"""语文培优 REST API。"""
import os
import re
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import sm2
from .auth import current_user, make_token, require_admin, verify_password
from .cards import KINDS, LEVELS, parse_import, validate_card
from .db import connect, init_db
from .grade import grade_answer

DATA_ROOT = Path(os.environ.get("DATA_ROOT", str(Path(__file__).resolve().parents[1] / "data")))
NEW_LIMIT = 8
TOTAL_LIMIT = 25
SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")

app = FastAPI(title="ccyuwen API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginBody(BaseModel):
    name: str
    password: str


class ImportBody(BaseModel):
    text: str
    resourceId: int | None = None


class DraftPatch(BaseModel):
    kind: str | None = None
    level: str | None = None
    prompt: str | None = None
    answer: str | None = None
    tags: str | None = None
    source: str | None = None
    status: str | None = None


class CourseBody(BaseModel):
    name: str
    note: str = ""
    kinds: list[str] = Field(default_factory=list)
    levels: list[str] = Field(default_factory=list)


class ReviewBody(BaseModel):
    pointId: int
    answer: str = ""
    reveal: bool = False


@app.on_event("startup")
def on_startup():
    (DATA_ROOT / "official").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "users").mkdir(parents=True, exist_ok=True)
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/login")
def login(body: LoginBody):
    with connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE name = %s", (body.name.strip(),)).fetchone()
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return {"token": make_token(user), "user": {"id": user["id"], "name": user["name"], "role": user["role"]}}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


@app.post("/api/resources")
def upload_resource(
    scope: str = Form("user"),
    file: UploadFile = File(...),
    user=Depends(current_user),
):
    if scope not in ("official", "user"):
        raise HTTPException(status_code=400, detail="scope 只能是 official 或 user")
    if scope == "official" and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="官方资源仅管理员可传")
    raw_name = Path(file.filename or "file").name
    safe = SAFE_NAME.sub("_", raw_name) or "file"
    year = str(date.today().year)
    if scope == "official":
        folder = DATA_ROOT / "official" / year
        owner_id = None
    else:
        folder = DATA_ROOT / "users" / str(user["id"])
        owner_id = user["id"]
    folder.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO resources (owner_type, owner_id, path, filename, mime, uploaded_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (scope, owner_id, "pending", safe, file.content_type, user["id"]),
        ).fetchone()
        rel = str(folder.relative_to(DATA_ROOT) / f"{row['id']}_{safe}")
        dest = DATA_ROOT / rel
        dest.write_bytes(file.file.read())
        conn.execute("UPDATE resources SET path = %s WHERE id = %s", (rel.replace("\\", "/"), row["id"]))
        conn.commit()
        saved = conn.execute("SELECT * FROM resources WHERE id = %s", (row["id"],)).fetchone()
    return saved


@app.get("/api/resources")
def list_resources(user=Depends(current_user)):
    with connect() as conn:
        if user["role"] == "admin":
            rows = conn.execute("SELECT * FROM resources ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM resources WHERE owner_type = 'user' AND owner_id = %s ORDER BY id DESC",
                (user["id"],),
            ).fetchall()
    return rows


@app.post("/api/drafts/import")
def import_drafts(body: ImportBody, user=Depends(require_admin)):
    parsed = parse_import(body.text)
    inserted = []
    with connect() as conn:
        resource_id = body.resourceId
        if resource_id:
            resource = conn.execute("SELECT * FROM resources WHERE id = %s", (resource_id,)).fetchone()
            if not resource:
                raise HTTPException(status_code=404, detail="资源不存在")
        for point in parsed["ok"]:
            row = conn.execute(
                """
                INSERT INTO knowledge_draft
                    (kind, level, prompt, answer, tags, source, source_resource_id, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    point["kind"],
                    point["level"],
                    point["prompt"],
                    point["answer"],
                    point["tags"],
                    point["source"],
                    resource_id,
                    user["id"],
                ),
            ).fetchone()
            inserted.append(row)
        if resource_id and inserted:
            conn.execute("UPDATE resources SET status = 'extracted' WHERE id = %s", (resource_id,))
        conn.commit()
    return {"ok": len(inserted), "skip": parsed["skip"], "items": inserted}


@app.get("/api/drafts")
def list_drafts(status: str = "draft", user=Depends(require_admin)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_draft WHERE status = %s ORDER BY id DESC",
            (status,),
        ).fetchall()
    return rows


@app.patch("/api/drafts/{draft_id}")
def patch_draft(draft_id: int, body: DraftPatch, user=Depends(require_admin)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM knowledge_draft WHERE id = %s", (draft_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="草稿不存在")
        merged = dict(row)
        payload = body.model_dump(exclude_unset=True)
        merged.update(payload)
        error = validate_card(merged["kind"], merged["prompt"], merged["answer"])
        if error:
            raise HTTPException(status_code=400, detail=error)
        conn.execute(
            """
            UPDATE knowledge_draft
            SET kind=%s, level=%s, prompt=%s, answer=%s, tags=%s, source=%s, status=%s
            WHERE id=%s
            """,
            (
                merged["kind"],
                merged["level"],
                merged["prompt"],
                merged["answer"],
                merged.get("tags") or "",
                merged.get("source") or "",
                merged.get("status") or row["status"],
                draft_id,
            ),
        )
        conn.commit()
        return conn.execute("SELECT * FROM knowledge_draft WHERE id = %s", (draft_id,)).fetchone()


@app.post("/api/drafts/{draft_id}/publish")
def publish_draft(draft_id: int, user=Depends(require_admin)):
    with connect() as conn:
        draft = conn.execute("SELECT * FROM knowledge_draft WHERE id = %s", (draft_id,)).fetchone()
        if not draft or draft["status"] == "discarded":
            raise HTTPException(status_code=404, detail="草稿不可发布")
        error = validate_card(draft["kind"], draft["prompt"], draft["answer"])
        if error:
            raise HTTPException(status_code=400, detail=error)
        existing = conn.execute(
            "SELECT id FROM knowledge_published WHERE prompt = %s AND answer = %s",
            (draft["prompt"], draft["answer"]),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE knowledge_published
                SET kind=%s, level=%s, tags=%s, source=%s, source_resource_id=%s, draft_id=%s, published_at=NOW()
                WHERE id=%s
                """,
                (
                    draft["kind"],
                    draft["level"],
                    draft["tags"],
                    draft["source"],
                    draft["source_resource_id"],
                    draft["id"],
                    existing["id"],
                ),
            )
            published_id = existing["id"]
        else:
            published = conn.execute(
                """
                INSERT INTO knowledge_published
                    (kind, level, prompt, answer, tags, source, source_resource_id, draft_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    draft["kind"],
                    draft["level"],
                    draft["prompt"],
                    draft["answer"],
                    draft["tags"],
                    draft["source"],
                    draft["source_resource_id"],
                    draft["id"],
                ),
            ).fetchone()
            published_id = published["id"]
        conn.execute("UPDATE knowledge_draft SET status = 'published' WHERE id = %s", (draft_id,))
        conn.commit()
        return conn.execute("SELECT * FROM knowledge_published WHERE id = %s", (published_id,)).fetchone()


@app.get("/api/library")
def library(
    kind: str | None = None,
    level: str | None = None,
    user=Depends(current_user),
):
    fields = "id, kind, level, prompt, tags, source, published_at"
    if user["role"] == "admin":
        fields = "id, kind, level, prompt, answer, tags, source, source_resource_id, draft_id, published_at"
    sql = "SELECT " + fields + " FROM knowledge_published WHERE 1=1"
    args = []
    if kind:
        sql += " AND kind = %s"
        args.append(kind)
    if level:
        sql += " AND level = %s"
        args.append(level)
    sql += " ORDER BY kind, level, id"
    with connect() as conn:
        return conn.execute(sql, args).fetchall()


@app.patch("/api/library/{point_id}")
def patch_published(point_id: int, body: DraftPatch, user=Depends(require_admin)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM knowledge_published WHERE id = %s", (point_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="知识点不存在")
        merged = dict(row)
        payload = body.model_dump(exclude_unset=True)
        payload.pop("status", None)
        merged.update(payload)
        if merged["kind"] not in KINDS or merged["level"] not in LEVELS:
            raise HTTPException(status_code=400, detail="类型或级别无效")
        error = validate_card(merged["kind"], merged["prompt"], merged["answer"])
        if error:
            raise HTTPException(status_code=400, detail=error)
        conn.execute(
            """
            UPDATE knowledge_published
            SET kind=%s, level=%s, prompt=%s, answer=%s, tags=%s, source=%s
            WHERE id=%s
            """,
            (
                merged["kind"],
                merged["level"],
                merged["prompt"],
                merged["answer"],
                merged.get("tags") or "",
                merged.get("source") or "",
                point_id,
            ),
        )
        conn.commit()
        return conn.execute("SELECT * FROM knowledge_published WHERE id = %s", (point_id,)).fetchone()


@app.post("/api/courses")
def create_course(body: CourseBody, user=Depends(current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写课程名称")
    kinds = [item for item in body.kinds if item in KINDS] or list(KINDS)
    levels = [item for item in body.levels if item in LEVELS] or list(LEVELS)
    with connect() as conn:
        points = conn.execute(
            """
            SELECT id FROM knowledge_published
            WHERE kind = ANY(%s) AND level = ANY(%s)
            ORDER BY kind, level, id
            """,
            (kinds, levels),
        ).fetchall()
        if not points:
            raise HTTPException(status_code=400, detail="没有符合条件的已发布知识点")
        course = conn.execute(
            "INSERT INTO courses (user_id, name, note) VALUES (%s, %s, %s) RETURNING *",
            (user["id"], name, body.note.strip()),
        ).fetchone()
        for index, point in enumerate(points):
            conn.execute(
                "INSERT INTO course_items (course_id, point_id, sort) VALUES (%s, %s, %s)",
                (course["id"], point["id"], index),
            )
        conn.commit()
        result = dict(course)
        result["itemCount"] = len(points)
        return result


@app.get("/api/courses")
def list_courses(user=Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT c.*, COUNT(i.point_id) AS item_count
            FROM courses c
            LEFT JOIN course_items i ON i.course_id = c.id
            WHERE c.user_id = %s
            GROUP BY c.id
            ORDER BY c.id DESC
            """,
            (user["id"],),
        ).fetchall()
    return rows


def _own_course(conn, course_id, user_id):
    course = conn.execute(
        "SELECT * FROM courses WHERE id = %s AND user_id = %s",
        (course_id, user_id),
    ).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course


@app.get("/api/courses/{course_id}/today")
def today_queue(course_id: int, user=Depends(current_user)):
    today = sm2.today_text()
    with connect() as conn:
        _own_course(conn, course_id, user["id"])
        points = conn.execute(
            """
            SELECT p.id, p.kind, p.level, p.prompt, p.tags, p.source,
                   s.n, s.ef, s.interval, s.due, s.lapses, s.last
            FROM course_items i
            JOIN knowledge_published p ON p.id = i.point_id
            LEFT JOIN review_state s
                ON s.point_id = p.id AND s.user_id = %s AND s.course_id = %s
            WHERE i.course_id = %s
            ORDER BY i.sort, p.id
            """,
            (user["id"], course_id, course_id),
        ).fetchall()
        failed_ids = {
            row["point_id"]
            for row in conn.execute(
                """
                SELECT DISTINCT ON (point_id) point_id, quality
                FROM review_log
                WHERE user_id = %s AND course_id = %s AND created_at::date = %s
                ORDER BY point_id, created_at DESC
                """,
                (user["id"], course_id, today),
            ).fetchall()
            if row["quality"] < 3
        }
    due, failed, fresh = [], [], []
    for point in points:
        item = serialize_point(point)
        if not point["last"]:
            fresh.append(item)
        elif str(point["due"] or "") <= today:
            due.append(item)
        elif point["id"] in failed_ids:
            failed.append(item)
    picked = due + failed
    for item in fresh:
        if len(picked) >= TOTAL_LIMIT:
            break
        new_count = sum(1 for card in picked if card.get("fresh"))
        if new_count >= NEW_LIMIT:
            break
        item["fresh"] = True
        picked.append(item)
    return {"today": today, "items": picked[:TOTAL_LIMIT], "due": len(due), "fresh": len(fresh)}


@app.post("/api/courses/{course_id}/review")
def review_point(course_id: int, body: ReviewBody, user=Depends(current_user)):
    today = sm2.today_text()
    with connect() as conn:
        _own_course(conn, course_id, user["id"])
        point = conn.execute(
            """
            SELECT p.*, s.n, s.ef, s.interval, s.due, s.lapses, s.last
            FROM course_items i
            JOIN knowledge_published p ON p.id = i.point_id
            LEFT JOIN review_state s
                ON s.point_id = p.id AND s.user_id = %s AND s.course_id = %s
            WHERE i.course_id = %s AND p.id = %s
            """,
            (user["id"], course_id, course_id, body.pointId),
        ).fetchone()
        if not point:
            raise HTTPException(status_code=404, detail="该课程没有这个知识点")
        is_new = point["last"] is None
        if body.reveal:
            result = grade_answer("", point["answer"])
            result["quality"] = 1
            result["correct"] = False
        else:
            result = grade_answer(body.answer, point["answer"])
        next_state = sm2.schedule(
            {"n": point["n"], "ef": point["ef"], "interval": point["interval"], "lapses": point["lapses"]},
            result["quality"],
            today,
        )
        conn.execute(
            """
            INSERT INTO review_state (user_id, course_id, point_id, n, ef, interval, due, lapses, last)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, course_id, point_id) DO UPDATE SET
                n = EXCLUDED.n, ef = EXCLUDED.ef, interval = EXCLUDED.interval,
                due = EXCLUDED.due, lapses = EXCLUDED.lapses, last = EXCLUDED.last
            """,
            (
                user["id"],
                course_id,
                body.pointId,
                next_state["n"],
                next_state["ef"],
                next_state["interval"],
                next_state["due"],
                next_state["lapses"],
                next_state["last"],
            ),
        )
        conn.execute(
            """
            INSERT INTO review_log (user_id, course_id, point_id, quality, is_new, correct)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user["id"], course_id, body.pointId, result["quality"], is_new, result["correct"]),
        )
        conn.commit()
    result["answer"] = point["answer"]
    result["state"] = next_state
    result["isNew"] = is_new
    return result


@app.get("/api/courses/{course_id}/stats")
def course_stats(course_id: int, user=Depends(current_user)):
    with connect() as conn:
        _own_course(conn, course_id, user["id"])
        rows = conn.execute(
            """
            SELECT p.id, p.kind, p.level, p.prompt,
                   s.n, s.interval, s.due, s.lapses, s.last,
                   COALESCE(SUM(CASE WHEN l.is_new THEN 1 ELSE 0 END), 0) AS study_count,
                   COALESCE(SUM(CASE WHEN NOT l.is_new THEN 1 ELSE 0 END), 0) AS review_count,
                   COALESCE(SUM(CASE WHEN l.correct THEN 0 ELSE 1 END), 0) AS error_count
            FROM course_items i
            JOIN knowledge_published p ON p.id = i.point_id
            LEFT JOIN review_state s
                ON s.point_id = p.id AND s.user_id = %s AND s.course_id = %s
            LEFT JOIN review_log l
                ON l.point_id = p.id AND l.user_id = %s AND l.course_id = %s
            WHERE i.course_id = %s
            GROUP BY p.id, p.kind, p.level, p.prompt, s.n, s.interval, s.due, s.lapses, s.last, i.sort
            ORDER BY i.sort, p.id
            """,
            (user["id"], course_id, user["id"], course_id, course_id),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["mastered"] = sm2.is_mastered(row)
        items.append(item)
    return {"items": items}


@app.get("/api/library/coverage")
def library_coverage(user=Depends(current_user)):
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM knowledge_published").fetchone()["n"]
        in_course = conn.execute(
            """
            SELECT COUNT(DISTINCT i.point_id) AS n
            FROM course_items i
            JOIN courses c ON c.id = i.course_id
            WHERE c.user_id = %s
            """,
            (user["id"],),
        ).fetchone()["n"]
        studied = conn.execute(
            """
            SELECT COUNT(DISTINCT point_id) AS n
            FROM review_log
            WHERE user_id = %s
            """,
            (user["id"],),
        ).fetchone()["n"]
        mastered = conn.execute(
            """
            SELECT COUNT(DISTINCT point_id) AS n FROM review_state
            WHERE user_id = %s AND (interval >= 21 OR n >= 5)
            """,
            (user["id"],),
        ).fetchone()["n"]
        by_kind = conn.execute(
            """
            SELECT p.kind, COUNT(*) AS total,
                   COUNT(DISTINCT CASE WHEN c.user_id = %s THEN i.point_id END) AS in_course
            FROM knowledge_published p
            LEFT JOIN course_items i ON i.point_id = p.id
            LEFT JOIN courses c ON c.id = i.course_id
            GROUP BY p.kind
            ORDER BY p.kind
            """,
            (user["id"],),
        ).fetchall()
    return {
        "total": total,
        "inCourse": in_course,
        "studied": studied,
        "mastered": mastered,
        "byKind": by_kind,
    }


def serialize_point(point):
    return {
        "id": point["id"],
        "kind": point["kind"],
        "level": point["level"],
        "prompt": point["prompt"],
        "tags": point["tags"],
        "source": point["source"],
        "fresh": not point["last"],
        "due": str(point["due"]) if point["due"] else None,
    }
