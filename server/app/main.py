"""语文培优 REST API。"""
import json
import os
import re
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import sm2
from .auth import current_user, make_token, require_admin, verify_password
from .cards import (
    GRADES,
    KIND_LABEL,
    KINDS,
    LEVELS,
    decode_filters,
    encode_filters,
    fill_group_fields,
    flatten_today_groups,
    normalize_grade,
    page_args,
    parse_energy_limit,
    parse_resource_filter,
    parse_import,
    plan_course_days,
    plan_today_groups,
    point_energy,
    validate_card,
)
from .db import connect, init_db
from .grade import grade_answer
from .materials import (
    PACKS,
    data_root,
    decorate_resource,
    find_pack,
    pack_status,
    summarize_sync,
    sync_all_official,
    sync_pack,
    upsert_published,
)

DATA_ROOT = Path(os.environ.get("DATA_ROOT", str(Path(__file__).resolve().parents[1] / "data")))
SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")
DEFAULT_CORS = (
    "http://localhost:8080,http://127.0.0.1:8080,"
    "http://localhost:5173,http://127.0.0.1:5173"
)


def cors_origins():
    raw = os.environ.get("CORS_ORIGINS", DEFAULT_CORS)
    return [item.strip() for item in raw.split(",") if item.strip()]


app = FastAPI(title="ccyuwen API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
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
    grade: str | None = None
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
    grades: list[str] = Field(default_factory=list)
    newEnergy: int = 30
    reviewEnergy: int = 30


class CoursePatch(BaseModel):
    name: str | None = None
    note: str | None = None
    newEnergy: int | None = None
    reviewEnergy: int | None = None


class CoursePreviewBody(BaseModel):
    kinds: list[str] = Field(default_factory=list)
    levels: list[str] = Field(default_factory=list)
    grades: list[str] = Field(default_factory=list)
    newEnergy: int = 30
    reviewEnergy: int = 30


class ReviewBody(BaseModel):
    pointId: int
    answer: str = ""
    reveal: bool = False


@app.on_event("startup")
def on_startup():
    if os.environ.get("JWT_SECRET", "ccyuwen-dev") == "ccyuwen-dev":
        print("warning: JWT_SECRET is the development default; set a new value before exposing the API")
    (DATA_ROOT / "official").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "users").mkdir(parents=True, exist_ok=True)
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/meta")
def meta():
    return {
        "kinds": [{"id": key, "label": KIND_LABEL[key]} for key in KINDS],
        "levels": list(LEVELS),
        "grades": list(GRADES),
    }


def decorate_library_item(row, hide_answer=False):
    data = dict(row)
    spec = find_pack(data.get("resource_slug") or "")
    if spec:
        data["resourceTitle"] = spec["title"]
    else:
        data["resourceTitle"] = data.get("resource_filename") or ""
    data["sourceResourceId"] = data.get("source_resource_id")
    data["pointKey"] = data.get("point_key") or ""
    data["groupKey"] = data.get("group_key") or ""
    data["subGroupKey"] = data.get("sub_group_key") or ""
    data["energy"] = point_energy(data)
    if hide_answer:
        data.pop("answer", None)
    return data


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
    scope: str = Form("official"),
    file: UploadFile = File(...),
    user=Depends(require_admin),
):
    if scope not in ("official", "user"):
        raise HTTPException(status_code=400, detail="scope 只能是 official 或 user")
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
                """
                SELECT * FROM resources
                WHERE owner_type = 'official'
                   OR (owner_type = 'user' AND owner_id = %s)
                ORDER BY id DESC
                """,
                (user["id"],),
            ).fetchall()
        status_by_slug = {}
        if user["role"] == "admin":
            with conn.cursor() as cur:
                status_by_slug = {spec["slug"]: pack_status(cur, spec) for spec in PACKS}
    items = [decorate_resource(row, status_by_slug) for row in rows]
    if user["role"] != "admin":
        for item in items:
            item.pop("path", None)
    return items


@app.post("/api/resources/sync-incremental")
def sync_incremental(user=Depends(require_admin)):
    with connect() as conn:
        with conn.cursor() as cur:
            results = sync_all_official(cur, force=False)
        conn.commit()
    return summarize_sync(results, "incremental")


@app.post("/api/resources/sync-all")
def sync_all_resources(user=Depends(require_admin)):
    with connect() as conn:
        with conn.cursor() as cur:
            results = sync_all_official(cur, force=True)
        conn.commit()
    return summarize_sync(results, "all")


@app.get("/api/resources/{resource_id}")
def get_resource(resource_id: int, user=Depends(require_admin)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM resources WHERE id = %s", (resource_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="资源不存在")
        linked = conn.execute(
            "SELECT COUNT(*) AS n FROM knowledge_published WHERE source_resource_id = %s",
            (resource_id,),
        ).fetchone()["n"]
    original = ""
    path = data_root() / row["path"]
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        if row["filename"].endswith(".json"):
            try:
                data = json.loads(text)
                original = str(data.get("original") or "")
            except json.JSONDecodeError:
                original = text
        else:
            original = text
    result = dict(row)
    result["linkedPoints"] = linked
    result["original"] = original
    return result


@app.post("/api/resources/{resource_id}/sync")
def sync_resource(resource_id: int, user=Depends(require_admin)):
    with connect() as conn:
        resource = conn.execute("SELECT * FROM resources WHERE id = %s", (resource_id,)).fetchone()
        if not resource:
            raise HTTPException(status_code=404, detail="资源不存在")
        with conn.cursor() as cur:
            spec = find_pack(resource.get("slug") or "")
            if spec:
                result = sync_pack(cur, spec, force=True)
            else:
                dest = data_root() / resource["path"]
                if not dest.is_file():
                    raise HTTPException(status_code=404, detail="资源文件不存在")
                parsed = parse_import(dest.read_text(encoding="utf-8"))
                inserted = 0
                updated = 0
                for point in parsed["ok"]:
                    _, status = upsert_published(cur, point, resource_id, force=True)
                    if status == "inserted":
                        inserted += 1
                    elif status == "updated":
                        updated += 1
                cur.execute("UPDATE resources SET status = 'extracted' WHERE id = %s", (resource_id,))
                result = {
                    "resourceId": resource_id,
                    "inserted": inserted,
                    "updated": updated,
                    "skip": parsed["skip"],
                    "total": len(parsed["ok"]),
                    "title": resource["filename"],
                }
        conn.commit()
    result["ok"] = (
        result.get("inserted", 0) + result.get("updated", 0) + result.get("unchanged", 0)
    )
    result["filename"] = resource["filename"]
    return result


@app.post("/api/resources/{resource_id}/file")
def replace_resource_file(
    resource_id: int,
    file: UploadFile = File(...),
    user=Depends(require_admin),
):
    with connect() as conn:
        resource = conn.execute("SELECT * FROM resources WHERE id = %s", (resource_id,)).fetchone()
        if not resource:
            raise HTTPException(status_code=404, detail="资源不存在")
        dest = data_root() / resource["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(file.file.read())
        conn.execute(
            "UPDATE resources SET mime = %s, status = 'stored' WHERE id = %s",
            (file.content_type, resource_id),
        )
        conn.commit()
        saved = conn.execute("SELECT * FROM resources WHERE id = %s", (resource_id,)).fetchone()
    return saved


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
                    (kind, level, grade, prompt, answer, tags, source, source_resource_id, created_by, point_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    point["kind"],
                    point["level"],
                    point.get("grade") or "",
                    point["prompt"],
                    point["answer"],
                    point["tags"],
                    point["source"],
                    resource_id,
                    user["id"],
                    point.get("key") or "",
                ),
            ).fetchone()
            inserted.append(row)
        if resource_id and inserted:
            conn.execute("UPDATE resources SET status = 'extracted' WHERE id = %s", (resource_id,))
        conn.commit()
    return {"ok": len(inserted), "skip": parsed["skip"], "items": inserted}


@app.get("/api/drafts")
def list_drafts(
    status: str = "draft",
    limit: int = 200,
    offset: int = 0,
    user=Depends(require_admin),
):
    safe_limit, safe_offset = page_args(limit, offset)
    with connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM knowledge_draft WHERE status = %s",
            (status,),
        ).fetchone()["n"]
        rows = conn.execute(
            """
            SELECT * FROM knowledge_draft
            WHERE status = %s
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (status, safe_limit, safe_offset),
        ).fetchall()
    return {"items": rows, "total": total, "limit": safe_limit, "offset": safe_offset}


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
            SET kind=%s, level=%s, grade=%s, prompt=%s, answer=%s, tags=%s, source=%s, status=%s
            WHERE id=%s
            """,
            (
                merged["kind"],
                merged["level"],
                normalize_grade(merged.get("grade")),
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
        grouped = fill_group_fields(
            {
                "key": draft.get("point_key") or "",
                "kind": draft["kind"],
                "level": draft["level"],
                "grade": normalize_grade(draft.get("grade")),
                "prompt": draft["prompt"],
                "answer": draft["answer"],
                "tags": draft.get("tags") or "",
                "source": draft.get("source") or "",
            }
        )
        existing = conn.execute(
            "SELECT id FROM knowledge_published WHERE prompt = %s AND answer = %s",
            (draft["prompt"], draft["answer"]),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE knowledge_published
                SET kind=%s, level=%s, grade=%s, tags=%s, source=%s, source_resource_id=%s,
                    draft_id=%s, point_key=%s, group_key=%s, sub_group_key=%s, published_at=NOW()
                WHERE id=%s
                """,
                (
                    draft["kind"],
                    draft["level"],
                    grouped["grade"],
                    draft["tags"],
                    draft["source"],
                    draft["source_resource_id"],
                    draft["id"],
                    grouped.get("key") or draft.get("point_key") or "",
                    grouped["group_key"],
                    grouped["sub_group_key"],
                    existing["id"],
                ),
            )
            published_id = existing["id"]
        else:
            published = conn.execute(
                """
                INSERT INTO knowledge_published
                    (kind, level, grade, prompt, answer, tags, source, source_resource_id, draft_id,
                     point_key, group_key, sub_group_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    draft["kind"],
                    draft["level"],
                    grouped["grade"],
                    draft["prompt"],
                    draft["answer"],
                    draft["tags"],
                    draft["source"],
                    draft["source_resource_id"],
                    draft["id"],
                    grouped.get("key") or draft.get("point_key") or "",
                    grouped["group_key"],
                    grouped["sub_group_key"],
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
    grade: str | None = None,
    kinds: str | None = None,
    levels: str | None = None,
    grades: str | None = None,
    resourceId: str | None = None,
    unlinked: bool = False,
    limit: int = 200,
    offset: int = 0,
    answers: bool = False,
    user=Depends(current_user),
):
    fields = (
        "k.id, k.kind, k.level, k.grade, k.prompt, k.answer, k.tags, k.source, "
        "k.point_key, k.group_key, k.sub_group_key, k.published_at, "
        "k.source_resource_id, k.draft_id, "
        "r.filename AS resource_filename, r.slug AS resource_slug"
    )
    hide_answer = user["role"] != "admin" and not answers
    kind_list = decode_filters(kinds, KINDS) if kinds else ([kind] if kind in KINDS else [])
    level_list = decode_filters(levels, LEVELS) if levels else ([level] if level in LEVELS else [])
    grade_list = decode_filters(grades, GRADES) if grades else ([grade] if grade in GRADES else [])
    where_sql = " FROM knowledge_published k LEFT JOIN resources r ON r.id = k.source_resource_id WHERE 1=1"
    args = []
    if kind_list:
        where_sql += " AND k.kind = ANY(%s)"
        args.append(kind_list)
    if level_list:
        where_sql += " AND k.level = ANY(%s)"
        args.append(level_list)
    if grade_list:
        where_sql += " AND k.grade = ANY(%s)"
        args.append(grade_list)
    resource_filter = parse_resource_filter(resourceId, unlinked)
    if resource_filter == 0:
        where_sql += " AND k.source_resource_id IS NULL"
    elif resource_filter:
        where_sql += " AND k.source_resource_id = %s"
        args.append(resource_filter)
    safe_limit, safe_offset = page_args(limit, offset)
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n" + where_sql, args).fetchone()["n"]
        rows = conn.execute(
            "SELECT " + fields + where_sql + " ORDER BY k.grade, k.kind, k.level, k.id LIMIT %s OFFSET %s",
            args + [safe_limit, safe_offset],
        ).fetchall()
    return {
        "items": [decorate_library_item(row, hide_answer=hide_answer) for row in rows],
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
    }


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
        merged["grade"] = normalize_grade(merged.get("grade"))
        error = validate_card(merged["kind"], merged["prompt"], merged["answer"])
        if error:
            raise HTTPException(status_code=400, detail=error)
        grouped = fill_group_fields(
            {
                "key": merged.get("point_key") or "",
                "kind": merged["kind"],
                "level": merged["level"],
                "grade": merged["grade"],
                "prompt": merged["prompt"],
                "answer": merged["answer"],
                "tags": merged.get("tags") or "",
                "source": merged.get("source") or "",
            }
        )
        conn.execute(
            """
            UPDATE knowledge_published
            SET kind=%s, level=%s, grade=%s, prompt=%s, answer=%s, tags=%s, source=%s,
                group_key=%s, sub_group_key=%s
            WHERE id=%s
            """,
            (
                merged["kind"],
                merged["level"],
                merged["grade"],
                merged["prompt"],
                merged["answer"],
                merged.get("tags") or "",
                merged.get("source") or "",
                grouped["group_key"],
                grouped["sub_group_key"],
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
    grades = [item for item in body.grades if item in GRADES]
    new_energy = parse_energy_limit(body.newEnergy)
    review_energy = parse_energy_limit(body.reviewEnergy)
    with connect() as conn:
        points = _candidate_points(conn, kinds, levels, grades)
        if not points:
            raise HTTPException(status_code=400, detail="没有符合条件的已发布知识点")
        course = conn.execute(
            """
            INSERT INTO courses (user_id, name, note, kinds, levels, grades, new_energy, review_energy)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                user["id"],
                name,
                body.note.strip(),
                encode_filters(kinds, KINDS),
                encode_filters(levels, LEVELS),
                encode_filters(grades, GRADES),
                new_energy,
                review_energy,
            ),
        ).fetchone()
        for index, point in enumerate(points):
            conn.execute(
                "INSERT INTO course_items (course_id, point_id, sort) VALUES (%s, %s, %s)",
                (course["id"], point["id"], index),
            )
        conn.commit()
        plan = plan_course_days(points, new_energy, review_energy)
        return serialize_course(course, len(points), plan)


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
    return [serialize_course(row, row["item_count"]) for row in rows]


@app.post("/api/courses/preview")
def preview_course(body: CoursePreviewBody, user=Depends(current_user)):
    kinds = [item for item in body.kinds if item in KINDS] or list(KINDS)
    levels = [item for item in body.levels if item in LEVELS] or list(LEVELS)
    grades = [item for item in body.grades if item in GRADES]
    new_energy = parse_energy_limit(body.newEnergy)
    review_energy = parse_energy_limit(body.reviewEnergy)
    with connect() as conn:
        points = _candidate_points(conn, kinds, levels, grades)
    plan = plan_course_days(points, new_energy, review_energy)
    return plan


def serialize_course(row, item_count=None, plan=None):
    data = dict(row)
    data["kinds"] = decode_filters(row.get("kinds"), KINDS)
    data["levels"] = decode_filters(row.get("levels"), LEVELS)
    data["grades"] = decode_filters(row.get("grades"), GRADES)
    data["newEnergy"] = int(row.get("new_energy") or 30)
    data["reviewEnergy"] = int(row.get("review_energy") or 30)
    count = item_count if item_count is not None else data.get("item_count")
    if count is not None:
        data["itemCount"] = int(count)
        data["item_count"] = int(count)
    if plan is not None:
        data["plan"] = plan
    return data


def _candidate_points(conn, kinds, levels, grades):
    sql = """
        SELECT id, kind, level, grade, prompt, answer, tags, source, point_key, group_key
        FROM knowledge_published
        WHERE kind = ANY(%s) AND level = ANY(%s)
        """
    args = [kinds, levels]
    if grades:
        sql += " AND grade = ANY(%s)"
        args.append(grades)
    sql += " ORDER BY grade, kind, level, id"
    return conn.execute(sql, args).fetchall()


def _course_plan_points(conn, course_id):
    return conn.execute(
        """
        SELECT p.id, p.kind, p.level, p.grade, p.prompt, p.answer, p.tags, p.source,
               p.point_key, p.group_key
        FROM course_items i
        JOIN knowledge_published p ON p.id = i.point_id
        WHERE i.course_id = %s
        ORDER BY i.sort, p.id
        """,
        (course_id,),
    ).fetchall()


def _own_course(conn, course_id, user_id):
    course = conn.execute(
        "SELECT * FROM courses WHERE id = %s AND user_id = %s",
        (course_id, user_id),
    ).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course


def _course_item_count(conn, course_id):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM course_items WHERE course_id = %s",
        (course_id,),
    ).fetchone()["n"]


@app.patch("/api/courses/{course_id}")
def patch_course(course_id: int, body: CoursePatch, user=Depends(current_user)):
    payload = body.model_dump(exclude_unset=True)
    if "name" in payload:
        payload["name"] = payload["name"].strip()
        if not payload["name"]:
            raise HTTPException(status_code=400, detail="请填写课程名称")
    if "note" in payload:
        payload["note"] = (payload["note"] or "").strip()
    new_energy = parse_energy_limit(payload.pop("newEnergy"), None) if "newEnergy" in payload else None
    review_energy = parse_energy_limit(payload.pop("reviewEnergy"), None) if "reviewEnergy" in payload else None
    if not payload and new_energy is None and review_energy is None:
        raise HTTPException(status_code=400, detail="没有要修改的字段")
    with connect() as conn:
        course = _own_course(conn, course_id, user["id"])
        merged = dict(course)
        merged.update(payload)
        if new_energy is not None:
            merged["new_energy"] = new_energy
        if review_energy is not None:
            merged["review_energy"] = review_energy
        conn.execute(
            """
            UPDATE courses
            SET name = %s, note = %s, new_energy = %s, review_energy = %s
            WHERE id = %s
            """,
            (
                merged["name"],
                merged["note"],
                merged.get("new_energy") or 30,
                merged.get("review_energy") or 30,
                course_id,
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM courses WHERE id = %s", (course_id,)).fetchone()
        return serialize_course(updated, _course_item_count(conn, course_id))


@app.delete("/api/courses/{course_id}")
def delete_course(course_id: int, user=Depends(current_user)):
    with connect() as conn:
        _own_course(conn, course_id, user["id"])
        conn.execute(
            "DELETE FROM review_log WHERE user_id = %s AND course_id = %s",
            (user["id"], course_id),
        )
        conn.execute(
            "DELETE FROM review_state WHERE user_id = %s AND course_id = %s",
            (user["id"], course_id),
        )
        conn.execute("DELETE FROM courses WHERE id = %s", (course_id,))
        conn.commit()
    return {"ok": True}


@app.post("/api/courses/{course_id}/sync")
def sync_course(course_id: int, user=Depends(current_user)):
    with connect() as conn:
        course = _own_course(conn, course_id, user["id"])
        kinds = decode_filters(course.get("kinds"), KINDS)
        levels = decode_filters(course.get("levels"), LEVELS)
        grades = decode_filters(course.get("grades"), GRADES)
        if not kinds or not levels:
            raise HTTPException(status_code=400, detail="旧课程没有筛选条件，请新建课程后再同步")
        existing = {
            row["point_id"]
            for row in conn.execute(
                "SELECT point_id FROM course_items WHERE course_id = %s",
                (course_id,),
            ).fetchall()
        }
        max_sort = conn.execute(
            "SELECT COALESCE(MAX(sort), -1) AS n FROM course_items WHERE course_id = %s",
            (course_id,),
        ).fetchone()["n"]
        sql = """
            SELECT id FROM knowledge_published
            WHERE kind = ANY(%s) AND level = ANY(%s)
            """
        args = [kinds, levels]
        if grades:
            sql += " AND grade = ANY(%s)"
            args.append(grades)
        sql += " ORDER BY grade, kind, level, id"
        candidates = conn.execute(sql, args).fetchall()
        added = 0
        for point in candidates:
            if point["id"] in existing:
                continue
            max_sort += 1
            conn.execute(
                "INSERT INTO course_items (course_id, point_id, sort) VALUES (%s, %s, %s)",
                (course_id, point["id"], max_sort),
            )
            added += 1
        conn.commit()
        count = _course_item_count(conn, course_id)
        result = serialize_course(course, count)
        result["added"] = added
        return result


@app.get("/api/courses/{course_id}/today")
def today_queue(course_id: int, user=Depends(current_user)):
    today = sm2.today_text()
    with connect() as conn:
        course = _own_course(conn, course_id, user["id"])
        points = conn.execute(
            """
            SELECT p.id, p.kind, p.level, p.grade, p.prompt, p.answer, p.tags, p.source,
                   p.point_key, p.group_key, p.sub_group_key,
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
    planned = plan_today_groups(
        points,
        failed_ids,
        today,
        course.get("new_energy") or 30,
        course.get("review_energy") or 30,
    )
    items = []
    for entry in flatten_today_groups(planned["groups"]):
        item = serialize_point(
            entry["row"],
            {
                "groupKey": entry["group_key"],
                "groupSize": entry["group_size"],
                "groupIndex": entry["group_index"],
                "taskIndex": entry["task_index"],
                "taskCount": entry["task_count"],
                "pointKey": entry["row"].get("point_key") or "",
                "energy": entry["energy"],
                "groupEnergy": entry["group_energy"],
                "part": entry["part"],
                "parts": entry["parts"],
                "cardTitle": entry["title"],
            },
        )
        items.append(item)
    return {
        "today": today,
        "items": items,
        "due": planned["due"],
        "fresh": planned["fresh"],
        "tasks": planned["tasks"],
        "cards": planned["cards"],
        "newEnergy": planned["newEnergy"],
        "reviewEnergy": planned["reviewEnergy"],
        "newBudget": planned["newBudget"],
        "reviewBudget": planned["reviewBudget"],
    }


@app.get("/api/courses/{course_id}/plan")
def course_plan(course_id: int, user=Depends(current_user)):
    with connect() as conn:
        course = _own_course(conn, course_id, user["id"])
        points = _course_plan_points(conn, course_id)
    plan = plan_course_days(points, course.get("new_energy") or 30, course.get("review_energy") or 30)
    plan["course"] = serialize_course(course, len(points))
    return plan


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
            SELECT p.id, p.kind, p.level, p.grade, p.prompt, p.source,
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
            GROUP BY p.id, p.kind, p.level, p.grade, p.prompt, p.source, s.n, s.interval, s.due, s.lapses, s.last, i.sort
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
            SELECT p.kind, COUNT(DISTINCT p.id) AS total,
                   COUNT(DISTINCT CASE WHEN c.user_id = %s THEN i.point_id END) AS in_course
            FROM knowledge_published p
            LEFT JOIN course_items i ON i.point_id = p.id
            LEFT JOIN courses c ON c.id = i.course_id
            GROUP BY p.kind
            ORDER BY p.kind
            """,
            (user["id"],),
        ).fetchall()
        by_grade = conn.execute(
            """
            SELECT COALESCE(NULLIF(p.grade, ''), '未分年级') AS grade, COUNT(DISTINCT p.id) AS total,
                   COUNT(DISTINCT CASE WHEN c.user_id = %s THEN i.point_id END) AS in_course
            FROM knowledge_published p
            LEFT JOIN course_items i ON i.point_id = p.id
            LEFT JOIN courses c ON c.id = i.course_id
            GROUP BY COALESCE(NULLIF(p.grade, ''), '未分年级')
            ORDER BY grade
            """,
            (user["id"],),
        ).fetchall()
    return {
        "total": total,
        "inCourse": in_course,
        "studied": studied,
        "mastered": mastered,
        "byKind": by_kind,
        "byGrade": by_grade,
    }


def serialize_point(point, extra=None):
    data = {
        "id": point["id"],
        "kind": point["kind"],
        "level": point["level"],
        "grade": point.get("grade") or "",
        "prompt": point["prompt"],
        "tags": point["tags"],
        "source": point["source"],
        "fresh": not point["last"],
        "due": str(point["due"]) if point["due"] else None,
        "pointKey": point.get("point_key") or "",
        "groupKey": point.get("group_key") or "",
        "subGroupKey": point.get("sub_group_key") or "",
        "energy": point_energy(point),
    }
    if extra:
        data.update(extra)
    return data
