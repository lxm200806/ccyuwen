"""语文培优 REST API。"""
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import sm2
from .auth import current_user, demo_hints_enabled, hash_password, make_token, require_admin, verify_password
from .study_modes import (
    MODE_OPTIONS,
    answer_lines,
    apply_today_mode,
    normalize_mode,
    resolve_default_mode,
    review_outcome,
)
from .progress import (
    build_progress,
    kid_feedback,
    mastery_counts,
    parent_copy,
    time_cap_state,
    week_brief,
)
from .family import (
    acting_student_id,
    ensure_parent_can_view,
    generate_link_code,
    is_parent,
    is_student,
    link_parent_to_student,
    list_linked_students,
    load_student,
    parse_minutes_cap,
    serialize_public_user,
)
from .wizard import list_wizard_grades, wizard_plan
from .cards import (
    GRADES,
    KIND_LABEL,
    KINDS,
    LEVELS,
    decode_filters,
    encode_filters,
    fill_group_fields,
    cluster_groups,
    flatten_today_groups,
    make_session,
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
from .entries import (
    AUDIENCE_LABEL,
    AUDIENCES,
    QUESTION_TYPE_LABEL,
    QUESTION_TYPES,
    audiences_for_grades,
    normalize_audience,
    normalize_question_type,
    parse_options,
    pick_course_cards,
)
from .db import connect, init_db
from .grade import grade_answer, grade_card
from .materials import (
    PACKS,
    attach_default_course,
    data_root,
    decorate_resource,
    find_pack,
    pack_status,
    summarize_sync,
    sync_all_official,
    sync_pack,
    upsert_entry,
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


class DraftIdsBody(BaseModel):
    ids: list[int] = Field(default_factory=list)


def pending_draft_exclusion(alias="k"):
    """Hide published rows that still have a matching unpublished draft."""
    return f"""
 AND NOT EXISTS (
    SELECT 1 FROM knowledge_draft d
    WHERE d.status = 'draft'
      AND (
        (
          NULLIF(BTRIM(COALESCE(d.point_key, '')), '') IS NOT NULL
          AND NULLIF(BTRIM(COALESCE({alias}.point_key, '')), '') IS NOT NULL
          AND d.point_key = {alias}.point_key
        )
        OR (d.prompt = {alias}.prompt AND d.answer = {alias}.answer)
      )
 )
"""


def unique_positive_ids(values):
    ids = []
    seen = set()
    for item in values or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in seen:
            seen.add(value)
            ids.append(value)
    return ids


def publish_draft_row(conn, draft_id):
    draft = conn.execute("SELECT * FROM knowledge_draft WHERE id = %s", (draft_id,)).fetchone()
    if not draft or draft["status"] == "discarded":
        raise HTTPException(status_code=404, detail="草稿不可发布")
    if draft["status"] == "published":
        existing = conn.execute(
            "SELECT * FROM knowledge_published WHERE draft_id = %s",
            (draft_id,),
        ).fetchone()
        if existing:
            return existing
        raise HTTPException(status_code=404, detail="草稿不可发布")
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
            "entry_key": draft.get("entry_key") or "",
            "lemma": draft.get("lemma") or "",
            "question_type": draft.get("question_type") or "dictation",
            "audience": draft.get("audience") or "all",
            "options": draft.get("options") or "",
        }
    )
    error = validate_card(
        grouped["kind"],
        grouped["prompt"],
        grouped["answer"],
        grouped.get("question_type"),
        grouped.get("lemma"),
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    with conn.cursor() as cur:
        published_id, _status = upsert_published(cur, grouped, draft.get("source_resource_id"), force=True)
        cur.execute("UPDATE knowledge_published SET draft_id = %s WHERE id = %s", (draft_id, published_id))
    conn.execute("UPDATE knowledge_draft SET status = 'published' WHERE id = %s", (draft_id,))
    with conn.cursor() as cur:
        attach_default_course(cur, [published_id])
    return conn.execute("SELECT * FROM knowledge_published WHERE id = %s", (published_id,)).fetchone()


class DraftPatch(BaseModel):
    kind: str | None = None
    level: str | None = None
    grade: str | None = None
    prompt: str | None = None
    answer: str | None = None
    tags: str | None = None
    source: str | None = None
    status: str | None = None
    questionType: str | None = None
    audience: str | None = None
    lemma: str | None = None
    options: Any = None


class CourseBody(BaseModel):
    name: str
    note: str = ""
    kinds: list[str] = Field(default_factory=list)
    levels: list[str] = Field(default_factory=list)
    grades: list[str] = Field(default_factory=list)
    newEnergy: int = 30
    reviewEnergy: int = 30
    reviewDefaultTest: bool = False
    dailyMinutesCap: int = 0
    studentId: int | None = None
    wizard: bool = False


class CoursePatch(BaseModel):
    name: str | None = None
    note: str | None = None
    newEnergy: int | None = None
    reviewEnergy: int | None = None
    reviewDefaultTest: bool | None = None
    dailyMinutesCap: int | None = None


class RegisterBody(BaseModel):
    name: str
    password: str
    role: str = "user"


class FamilyLinkBody(BaseModel):
    studentName: str
    linkCode: str


class StudyTimeBody(BaseModel):
    seconds: int = 0


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
    mode: str = "learn"


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
        "questionTypes": [{"id": key, "label": QUESTION_TYPE_LABEL[key]} for key in QUESTION_TYPES],
        "audiences": [{"id": key, "label": AUDIENCE_LABEL[key]} for key in AUDIENCES],
        "demoHints": demo_hints_enabled(),
        "studyModes": list(MODE_OPTIONS),
        "wizard": list_wizard_grades(),
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
    data["entryKey"] = data.get("entry_key") or ""
    data["lemma"] = data.get("lemma") or ""
    data["questionType"] = data.get("question_type") or "dictation"
    data["audience"] = data.get("audience") or "all"
    data["options"] = parse_options(data.get("options"))
    data["energy"] = point_energy(data)
    data["entryGrades"] = data.get("entry_grades") or ""
    data["entryLevels"] = data.get("entry_levels") or ""
    if hide_answer:
        data.pop("answer", None)
    return data


def _user_payload(conn, user_row):
    data = {"id": user_row["id"], "name": user_row["name"], "role": user_row["role"]}
    if is_student(user_row):
        data["linkCode"] = user_row.get("link_code") or ""
    if is_parent(user_row):
        data["students"] = [
            serialize_public_user(row) for row in list_linked_students(conn, user_row["id"])
        ]
    return data


@app.post("/api/login")
def login(body: LoginBody):
    with connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE name = %s", (body.name.strip(),)).fetchone()
        if not user or not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="账号或密码错误")
        payload = _user_payload(conn, user)
    return {"token": make_token(user), "user": payload}


@app.post("/api/register")
def register(body: RegisterBody):
    name = body.name.strip()
    password = body.password.strip()
    role = (body.role or "user").strip()
    if role not in ("user", "parent"):
        raise HTTPException(status_code=400, detail="只能注册学生或家长账号")
    if len(name) < 2 or len(name) > 32:
        raise HTTPException(status_code=400, detail="账号请用 2 到 32 个字")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="密码至少 4 位")
    with connect() as conn:
        existing = conn.execute("SELECT id FROM users WHERE name = %s", (name,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="这个账号已经有人用了")
        code = generate_link_code() if role == "user" else ""
        row = conn.execute(
            """
            INSERT INTO users (name, password_hash, role, link_code)
            VALUES (%s, %s, %s, %s)
            RETURNING *
            """,
            (name, hash_password(password), role, code),
        ).fetchone()
        conn.commit()
        payload = _user_payload(conn, row)
    return {"token": make_token(row), "user": payload}


@app.get("/api/me")
def me(user=Depends(current_user)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = %s", (user["id"],)).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="登录已失效")
        return _user_payload(conn, row)


@app.get("/api/family")
def family_home(user=Depends(current_user)):
    if not is_parent(user):
        raise HTTPException(status_code=403, detail="需要家长账号")
    today = sm2.today_text()
    with connect() as conn:
        students = []
        for student in list_linked_students(conn, user["id"]):
            courses = _list_student_courses(conn, student["id"], today)
            students.append(
                {
                    "id": student["id"],
                    "name": student["name"],
                    "courses": courses,
                    "today": _student_today_rollups(courses),
                    "week": _student_week_rollup(conn, student["id"], today),
                }
            )
        conn.commit()
    return {"students": students}


@app.post("/api/family/link")
def family_link(body: FamilyLinkBody, user=Depends(current_user)):
    if not is_parent(user):
        raise HTTPException(status_code=403, detail="需要家长账号")
    with connect() as conn:
        student = link_parent_to_student(conn, user["id"], body.studentName, body.linkCode)
        conn.commit()
        return serialize_public_user(student)


@app.get("/api/wizard")
def course_wizard(grade: str = "", user=Depends(current_user)):
    if is_parent(user) or is_student(user) or user.get("role") == "admin":
        plan = wizard_plan(grade) if grade else None
        return {"grades": list_wizard_grades(), "plan": plan}
    raise HTTPException(status_code=403, detail="没有权限")


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
                    (kind, level, grade, prompt, answer, tags, source, source_resource_id, created_by, point_key,
                     group_key, sub_group_key, entry_key, lemma, question_type, audience, options)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    point.get("group_key") or "",
                    point.get("sub_group_key") or "",
                    point.get("entry_key") or "",
                    point.get("lemma") or "",
                    point.get("question_type") or "dictation",
                    point.get("audience") or "all",
                    point.get("options") or "",
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


@app.post("/api/drafts/publish-batch")
def publish_drafts_batch(body: DraftIdsBody, user=Depends(require_admin)):
    ids = unique_positive_ids(body.ids)
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要发布的草稿")
    published = []
    errors = []
    with connect() as conn:
        for draft_id in ids:
            try:
                published.append(publish_draft_row(conn, draft_id))
            except HTTPException as exc:
                errors.append({"id": draft_id, "detail": exc.detail})
        conn.commit()
    return {"ok": len(published), "fail": len(errors), "items": published, "errors": errors}


@app.post("/api/drafts/{draft_id}/publish")
def publish_draft(draft_id: int, user=Depends(require_admin)):
    with connect() as conn:
        row = publish_draft_row(conn, draft_id)
        conn.commit()
        return row


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
    questionType: str | None = None,
    audience: str | None = None,
    limit: int = 200,
    offset: int = 0,
    answers: bool = False,
    user=Depends(current_user),
):
    fields = (
        "k.id, k.kind, k.level, k.grade, k.prompt, k.answer, k.tags, k.source, "
        "k.point_key, k.group_key, k.sub_group_key, k.published_at, "
        "k.source_resource_id, k.draft_id, k.entry_key, k.lemma, k.question_type, k.audience, k.options, "
        "r.filename AS resource_filename, r.slug AS resource_slug, "
        "e.grades AS entry_grades, e.levels AS entry_levels"
    )
    hide_answer = user["role"] != "admin" and not answers
    kind_list = decode_filters(kinds, KINDS) if kinds else ([kind] if kind in KINDS else [])
    level_list = decode_filters(levels, LEVELS) if levels else ([level] if level in LEVELS else [])
    use_entry_grades = bool(grades)
    grade_list = decode_filters(grades, GRADES) if use_entry_grades else ([grade] if grade in GRADES else [])
    where_sql = (
        " FROM knowledge_published k "
        "LEFT JOIN resources r ON r.id = k.source_resource_id "
        "LEFT JOIN knowledge_entry e ON e.entry_key = k.entry_key AND k.entry_key <> '' "
        "WHERE 1=1"
    )
    args = []
    if kind_list:
        where_sql += " AND k.kind = ANY(%s)"
        args.append(kind_list)
    if level_list:
        where_sql += " AND k.level = ANY(%s)"
        args.append(level_list)
    where_sql, args = _append_grade_filter(where_sql, args, grade_list, via_entry=use_entry_grades)
    if use_entry_grades:
        wanted = audiences_for_grades(grade_list)
        if wanted:
            where_sql += " AND k.audience = ANY(%s)"
            args.append(list(wanted))
    qtype = normalize_question_type(questionType) if questionType else ""
    if questionType and qtype in QUESTION_TYPES:
        where_sql += " AND k.question_type = %s"
        args.append(qtype)
    aud = normalize_audience(audience) if audience else ""
    if audience and aud in AUDIENCES:
        where_sql += " AND k.audience = %s"
        args.append(aud)
    resource_filter = parse_resource_filter(resourceId, unlinked)
    if resource_filter == 0:
        where_sql += " AND k.source_resource_id IS NULL"
    elif resource_filter:
        where_sql += " AND k.source_resource_id = %s"
        args.append(resource_filter)
    where_sql += pending_draft_exclusion("k")
    safe_limit, safe_offset = page_args(limit, offset)
    with connect() as conn:
        if use_entry_grades:
            rows = conn.execute(
                "SELECT " + fields + where_sql + " ORDER BY k.grade, k.kind, k.entry_key, k.question_type, k.id",
                args,
            ).fetchall()
            picked = pick_course_cards(rows, grade_list)
            total = len(picked)
            entry_count = _entry_count_from_rows(picked)
            page = picked[safe_offset : safe_offset + safe_limit]
        else:
            total = conn.execute("SELECT COUNT(*) AS n" + where_sql, args).fetchone()["n"]
            entry_count = conn.execute(
                """
                SELECT COUNT(DISTINCT CASE WHEN k.entry_key <> '' THEN k.entry_key ELSE 'id:' || k.id::text END) AS n
                """
                + where_sql,
                args,
            ).fetchone()["n"]
            page = conn.execute(
                "SELECT " + fields + where_sql + " ORDER BY k.grade, k.kind, k.entry_key, k.question_type, k.id LIMIT %s OFFSET %s",
                args + [safe_limit, safe_offset],
            ).fetchall()
    return {
        "items": [decorate_library_item(row, hide_answer=hide_answer) for row in page],
        "total": total,
        "entryCount": entry_count,
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
        if "questionType" in payload:
            merged["question_type"] = payload["questionType"]
        if "audience" in payload:
            merged["audience"] = payload["audience"]
        merged["grade"] = normalize_grade(merged.get("grade"))
        error = validate_card(
            merged["kind"],
            merged["prompt"],
            merged["answer"],
            merged.get("question_type") or merged.get("questionType"),
            merged.get("lemma"),
        )
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
                "entry_key": merged.get("entry_key") or merged.get("entryKey") or "",
                "lemma": merged.get("lemma") or "",
                "question_type": merged.get("question_type") or merged.get("questionType") or "dictation",
                "audience": merged.get("audience") or "all",
                "options": merged.get("options") or "",
            }
        )
        with conn.cursor() as cur:
            upsert_entry(cur, grouped)
        conn.execute(
            """
            UPDATE knowledge_published
            SET kind=%s, level=%s, grade=%s, prompt=%s, answer=%s, tags=%s, source=%s,
                group_key=%s, sub_group_key=%s, entry_key=%s, lemma=%s, question_type=%s,
                audience=%s, options=%s
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
                grouped.get("entry_key") or "",
                grouped.get("lemma") or "",
                grouped.get("question_type") or "dictation",
                grouped.get("audience") or "all",
                grouped.get("options") or "",
                point_id,
            ),
        )
        conn.commit()
        return conn.execute("SELECT * FROM knowledge_published WHERE id = %s", (point_id,)).fetchone()


@app.post("/api/courses")
def create_course(body: CourseBody, user=Depends(current_user)):
    plan = wizard_plan(body.grades[0]) if body.wizard and body.grades else None
    name = body.name.strip() or (plan["name"] if plan else "")
    if not name:
        raise HTTPException(status_code=400, detail="请填写课程名称")
    kinds = [item for item in (plan["kinds"] if plan and not body.kinds else body.kinds) if item in KINDS] or list(KINDS)
    levels = [item for item in (plan["levels"] if plan and not body.levels else body.levels) if item in LEVELS] or list(LEVELS)
    grades = [item for item in body.grades if item in GRADES]
    if plan and not grades:
        grades = [plan["grade"]]
    new_energy = parse_energy_limit(plan["newEnergy"] if plan and body.wizard else body.newEnergy)
    review_energy = parse_energy_limit(plan["reviewEnergy"] if plan and body.wizard else body.reviewEnergy)
    minutes_cap = parse_minutes_cap(body.dailyMinutesCap, plan["minutes"] if plan else 0)
    note = body.note.strip() or (plan["note"] if plan else "")
    with connect() as conn:
        owner_id = _owner_id_for_write(conn, user, body.studentId)
        points = _candidate_points(conn, kinds, levels, grades)
        if not points:
            raise HTTPException(status_code=400, detail="没有符合条件的已发布知识点")
        course = conn.execute(
            """
            INSERT INTO courses (user_id, name, note, kinds, levels, grades, new_energy, review_energy, review_default_test, daily_minutes_cap)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                owner_id,
                name,
                note,
                encode_filters(kinds, KINDS),
                encode_filters(levels, LEVELS),
                encode_filters(grades, GRADES),
                new_energy,
                review_energy,
                bool(body.reviewDefaultTest),
                minutes_cap,
            ),
        ).fetchone()
        for index, point in enumerate(points):
            conn.execute(
                "INSERT INTO course_items (course_id, point_id, sort) VALUES (%s, %s, %s)",
                (course["id"], point["id"], index),
            )
        conn.commit()
        plan = plan_course_days(points, new_energy, review_energy)
        return serialize_course(course, len(points), plan, published_count=len(points))


@app.get("/api/courses")
def list_courses(studentId: int | None = None, user=Depends(current_user)):
    today = sm2.today_text()
    with connect() as conn:
        owner_id = _owner_id_for_write(conn, user, studentId) if is_parent(user) else int(user["id"])
        results = _list_student_courses(conn, owner_id, today)
        conn.commit()
    return results


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


def serialize_course(row, item_count=None, plan=None, published_count=None, progress=None, week=None):
    data = dict(row)
    data["kinds"] = decode_filters(row.get("kinds"), KINDS)
    data["levels"] = decode_filters(row.get("levels"), LEVELS)
    data["grades"] = decode_filters(row.get("grades"), GRADES)
    data["newEnergy"] = int(row.get("new_energy") or 30)
    data["reviewEnergy"] = int(row.get("review_energy") or 30)
    data["reviewDefaultTest"] = bool(row.get("review_default_test"))
    data["dailyMinutesCap"] = int(row.get("daily_minutes_cap") or 0)
    data["studentId"] = int(row.get("user_id") or 0)
    data["isDefault"] = _is_default_course(row)
    count = item_count if item_count is not None else data.get("item_count")
    if count is not None:
        data["itemCount"] = int(count)
        data["item_count"] = int(count)
    if published_count is not None:
        data["publishedCount"] = int(published_count)
        data["pendingCount"] = max(0, int(published_count) - int(data.get("itemCount") or 0))
    if plan is not None:
        data["plan"] = plan
    if progress is not None:
        data["progress"] = progress
    if week is not None:
        data["week"] = week
    return data


def _is_default_course(course):
    return (course.get("name") or "") == "默认课程"


def _course_filters(course):
    kinds = decode_filters(course.get("kinds"), KINDS) or list(KINDS)
    levels = decode_filters(course.get("levels"), LEVELS) or list(LEVELS)
    grades = decode_filters(course.get("grades"), GRADES)
    return kinds, levels, grades


def _append_grade_filter(sql, args, grades, alias="k", via_entry=False):
    if not grades:
        return sql, args
    if via_entry:
        sql += f"""
         AND (
            {alias}.grade = ANY(%s)
            OR EXISTS (
                SELECT 1 FROM knowledge_entry_grade g
                WHERE g.entry_key = {alias}.entry_key
                  AND {alias}.entry_key <> ''
                  AND g.grade = ANY(%s)
            )
         )
        """
        return sql, args + [grades, grades]
    return sql + f" AND {alias}.grade = ANY(%s)", args + [grades]


def _entry_count_from_rows(rows):
    keys = set()
    for row in rows or []:
        key = str(row.get("entry_key") or "").strip() or ("id:" + str(row.get("id") or ""))
        keys.add(key)
    return len(keys)


def _matching_published_count(conn, course):
    kinds, levels, grades = _course_filters(course)
    return len(_candidate_points(conn, kinds, levels, grades))


def _sync_course_items(conn, course):
    kinds, levels, grades = _course_filters(course)
    if not decode_filters(course.get("kinds"), KINDS) or not decode_filters(course.get("levels"), LEVELS):
        if not _is_default_course(course):
            return 0
    course_id = course["id"]
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
    added = 0
    points = _candidate_points(conn, kinds, levels, grades)
    for point in points:
        if point["id"] in existing:
            continue
        max_sort += 1
        conn.execute(
            "INSERT INTO course_items (course_id, point_id, sort) VALUES (%s, %s, %s)",
            (course_id, point["id"], max_sort),
        )
        added += 1
    removed = _prune_duplicate_course_items(conn, course_id, points)
    return added + removed


def _ensure_default_synced(conn, course):
    if not _is_default_course(course):
        return course, 0
    added = _sync_course_items(conn, course)
    if added:
        conn.commit()
    return course, added


def _prune_duplicate_course_items(conn, course_id, points):
    canonical = {}
    for point in points or []:
        key = (
            str(point.get("entry_key") or "") or ("id:" + str(point.get("id") or "")),
            normalize_question_type(point.get("question_type")),
        )
        canonical[key] = point["id"]
    if not canonical:
        return 0
    extras = conn.execute(
        """
        SELECT i.point_id, p.entry_key, p.question_type
        FROM course_items i
        JOIN knowledge_published p ON p.id = i.point_id
        WHERE i.course_id = %s
        """,
        (course_id,),
    ).fetchall()
    removed = 0
    for row in extras:
        key = (
            str(row.get("entry_key") or "") or ("id:" + str(row.get("point_id") or "")),
            normalize_question_type(row.get("question_type")),
        )
        keep_id = canonical.get(key)
        if keep_id and row["point_id"] != keep_id:
            conn.execute(
                "DELETE FROM course_items WHERE course_id = %s AND point_id = %s",
                (course_id, row["point_id"]),
            )
            removed += 1
    return removed


def _candidate_points(conn, kinds, levels, grades):
    sql = """
        SELECT id, kind, level, grade, prompt, answer, tags, source, point_key, group_key,
               entry_key, lemma, question_type, audience, options
        FROM knowledge_published k
        WHERE kind = ANY(%s) AND level = ANY(%s)
        """
    args = [kinds, levels]
    sql, args = _append_grade_filter(sql, args, grades, via_entry=True)
    wanted = audiences_for_grades(grades)
    if wanted:
        sql += " AND audience = ANY(%s)"
        args.append(list(wanted))
    sql += pending_draft_exclusion("k")
    sql += " ORDER BY grade, kind, entry_key, question_type, id"
    return pick_course_cards(conn.execute(sql, args).fetchall(), grades)


def _course_plan_points(conn, course_id):
    return conn.execute(
        """
        SELECT p.id, p.kind, p.level, p.grade, p.prompt, p.answer, p.tags, p.source,
               p.point_key, p.group_key, p.entry_key, p.lemma, p.question_type, p.audience, p.options
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


def _accessible_course(conn, course_id, user, student_only=False):
    """学生看自己的课；家长看已关联孩子的课。默写练习仍只允许学生。"""
    course = conn.execute("SELECT * FROM courses WHERE id = %s", (course_id,)).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    owner_id = int(course["user_id"])
    if is_parent(user):
        if student_only:
            raise HTTPException(status_code=403, detail="请让孩子打开今日默写")
        ensure_parent_can_view(conn, user, owner_id)
        return course
    if int(user["id"]) != owner_id:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course


def _owner_id_for_write(conn, user, student_id=None):
    if is_parent(user):
        owner_id = acting_student_id(user, student_id)
        ensure_parent_can_view(conn, user, owner_id)
        return owner_id
    return int(user["id"])


def _list_student_courses(conn, student_id, today):
    rows = conn.execute(
        """
        SELECT c.*, COUNT(i.point_id) AS item_count
        FROM courses c
        LEFT JOIN course_items i ON i.course_id = c.id
        WHERE c.user_id = %s
        GROUP BY c.id
        ORDER BY c.id DESC
        """,
        (student_id,),
    ).fetchall()
    results = []
    for row in rows:
        course = dict(row)
        if _is_default_course(course):
            added = _sync_course_items(conn, course)
            if added:
                course["item_count"] = _course_item_count(conn, course["id"])
        progress = _course_today_progress(conn, course, student_id, today)
        week = _course_week_brief(conn, course["id"], student_id, today)
        progress = _attach_time_cap(conn, course, student_id, today, progress)
        results.append(
            serialize_course(
                course,
                course["item_count"],
                published_count=_matching_published_count(conn, course),
                progress=progress,
                week=week,
            )
        )
    return results


def _student_today_rollups(courses):
    remaining_new = 0
    remaining_review = 0
    practiced = 0
    weak = []
    summaries = []
    for course in courses or []:
        progress = course.get("progress") or {}
        remaining_new += int(progress.get("remainingNewEnergy") or 0)
        remaining_review += int(progress.get("remainingReviewEnergy") or 0)
        practiced += int(progress.get("todayPracticed") or 0)
        if progress.get("summary"):
            summaries.append(progress["summary"])
        for item in progress.get("weakKinds") or []:
            weak.append(item)
    weak_labels = []
    seen = set()
    for item in weak:
        label = item.get("label") or item.get("kind")
        if label and label not in seen:
            seen.add(label)
            weak_labels.append(label)
    if not courses:
        title = "还没有课程"
        summary = "先用年级向导给孩子组一份课。"
    elif practiced <= 0 and remaining_new == 0 and remaining_review == 0:
        title = "今天还没开始练"
        summary = summaries[0] if summaries else "今天还没开始练。"
    elif remaining_new or remaining_review:
        title = "还差" + ("、".join(
            part
            for part in (
                ("新学 %s 能" % remaining_new) if remaining_new else "",
                ("复习 %s 能" % remaining_review) if remaining_review else "",
            )
            if part
        ))
        summary = summaries[0] if summaries else title
    else:
        title = "今天练完了"
        summary = summaries[0] if summaries else "今天练完了。"
    return {
        "title": title,
        "summary": summary,
        "remainingNewEnergy": remaining_new,
        "remainingReviewEnergy": remaining_review,
        "todayPracticed": practiced,
        "weakKinds": [{"label": label} for label in weak_labels[:3]],
    }


def _student_week_rollup(conn, student_id, today):
    logs = conn.execute(
        """
        SELECT l.correct, l.created_at, p.kind
        FROM review_log l
        JOIN knowledge_published p ON p.id = l.point_id
        WHERE l.user_id = %s AND l.created_at >= (CURRENT_DATE - INTERVAL '6 days')
        ORDER BY l.created_at
        """,
        (student_id,),
    ).fetchall()
    return week_brief(logs, today=date.fromisoformat(today) if isinstance(today, str) else today)


def _course_week_brief(conn, course_id, user_id, today):
    logs = conn.execute(
        """
        SELECT l.correct, l.created_at, p.kind
        FROM review_log l
        JOIN knowledge_published p ON p.id = l.point_id
        WHERE l.user_id = %s AND l.course_id = %s
          AND l.created_at >= (CURRENT_DATE - INTERVAL '6 days')
        ORDER BY l.created_at
        """,
        (user_id, course_id),
    ).fetchall()
    return week_brief(logs, today=date.fromisoformat(today) if isinstance(today, str) else today)


def _load_study_seconds(conn, course_id, user_id, today):
    row = conn.execute(
        "SELECT seconds FROM study_time WHERE user_id = %s AND course_id = %s AND day = %s",
        (user_id, course_id, today),
    ).fetchone()
    return int((row or {}).get("seconds") or 0)


def _attach_time_cap(conn, course, user_id, today, progress):
    data = dict(progress or {})
    data.update(time_cap_state(_load_study_seconds(conn, course["id"], user_id, today), course.get("daily_minutes_cap")))
    return data


def _wrong_book_rows(conn, course_id, user_id, limit=40):
    return conn.execute(
        """
        SELECT p.id, p.kind, p.level, p.grade, p.prompt, p.tags, p.source,
               COUNT(*) FILTER (WHERE NOT l.correct) AS error_count,
               MAX(l.created_at) FILTER (WHERE NOT l.correct) AS last_wrong,
               MAX(l.created_at) AS last_attempt
        FROM review_log l
        JOIN knowledge_published p ON p.id = l.point_id
        JOIN course_items i ON i.course_id = %s AND i.point_id = p.id
        WHERE l.user_id = %s AND l.course_id = %s
          AND l.created_at >= (CURRENT_DATE - INTERVAL '21 days')
        GROUP BY p.id, p.kind, p.level, p.grade, p.prompt, p.tags, p.source
        HAVING COUNT(*) FILTER (WHERE NOT l.correct) > 0
        ORDER BY last_wrong DESC NULLS LAST, error_count DESC, p.id
        LIMIT %s
        """,
        (course_id, user_id, course_id, limit),
    ).fetchall()


def _plan_wrong_book(points):
    groups = []
    for group in cluster_groups(points):
        session = make_session(group, group["rows"])
        session["role"] = "review"
        groups.append(session)
    energy = sum(int(group.get("energy") or 0) for group in groups)
    return {
        "groups": groups,
        "due": len(groups),
        "failed": len(groups),
        "fresh": 0,
        "tasks": len(groups),
        "cards": sum(len(group.get("rows") or []) for group in groups),
        "newEnergy": 0,
        "reviewEnergy": energy,
        "newBudget": 0,
        "reviewBudget": energy,
    }


def _wrong_book_items(rows):
    items = []
    for row in rows or []:
        items.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "kindLabel": KIND_LABEL.get(row["kind"], row["kind"]),
                "level": row.get("level") or "",
                "grade": row.get("grade") or "",
                "prompt": row["prompt"],
                "errorCount": int(row.get("error_count") or 0),
                "lastWrong": str(row["last_wrong"]) if row.get("last_wrong") else "",
            }
        )
    return items


def _course_item_count(conn, course_id):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM course_items WHERE course_id = %s",
        (course_id,),
    ).fetchone()["n"]


def _course_review_pref(course):
    return bool(course.get("review_default_test"))


def _load_today_points(conn, course_id, user_id):
    return conn.execute(
        """
        SELECT p.id, p.kind, p.level, p.grade, p.prompt, p.answer, p.tags, p.source,
               p.point_key, p.group_key, p.sub_group_key, p.entry_key, p.lemma,
               p.question_type, p.audience, p.options,
               s.n, s.ef, s.interval, s.due, s.lapses, s.last
        FROM course_items i
        JOIN knowledge_published p ON p.id = i.point_id
        LEFT JOIN review_state s
            ON s.point_id = p.id AND s.user_id = %s AND s.course_id = %s
        WHERE i.course_id = %s
        ORDER BY i.sort, p.id
        """,
        (user_id, course_id, course_id),
    ).fetchall()


def _load_today_logs(conn, course_id, user_id, today):
    return conn.execute(
        """
        SELECT l.point_id, l.quality, l.correct, l.is_new, l.created_at, p.kind
        FROM review_log l
        JOIN knowledge_published p ON p.id = l.point_id
        WHERE l.user_id = %s AND l.course_id = %s AND l.created_at::date = %s
        ORDER BY l.created_at, l.id
        """,
        (user_id, course_id, today),
    ).fetchall()


def _failed_ids_from_logs(logs):
    latest = {}
    for row in logs or []:
        latest[row["point_id"]] = int(row["quality"] or 0)
    return {point_id for point_id, quality in latest.items() if quality < 3}


def _plan_course_today(conn, course, user_id, today):
    points = _load_today_points(conn, course["id"], user_id)
    logs = _load_today_logs(conn, course["id"], user_id, today)
    planned = plan_today_groups(
        points,
        _failed_ids_from_logs(logs),
        today,
        course.get("new_energy") or 30,
        course.get("review_energy") or 30,
    )
    return points, logs, planned


def _course_today_progress(conn, course, user_id, today, planned=None, logs=None, item_count=None, mastery=None):
    if planned is None or logs is None:
        points, logs, planned = _plan_course_today(conn, course, user_id, today)
        item_count = len(points) if item_count is None else item_count
    return build_progress(
        planned,
        logs,
        item_count=item_count if item_count is not None else 0,
        mastered=None if mastery is None else mastery.get("mastered"),
        total=None if mastery is None else mastery.get("total"),
    )


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
    review_pref = payload.pop("reviewDefaultTest") if "reviewDefaultTest" in payload else None
    minutes_cap = parse_minutes_cap(payload.pop("dailyMinutesCap"), None) if "dailyMinutesCap" in payload else None
    if not payload and new_energy is None and review_energy is None and review_pref is None and minutes_cap is None:
        raise HTTPException(status_code=400, detail="没有要修改的字段")
    with connect() as conn:
        course = _accessible_course(conn, course_id, user)
        merged = dict(course)
        merged.update(payload)
        if new_energy is not None:
            merged["new_energy"] = new_energy
        if review_energy is not None:
            merged["review_energy"] = review_energy
        if review_pref is not None:
            merged["review_default_test"] = bool(review_pref)
        if minutes_cap is not None:
            merged["daily_minutes_cap"] = minutes_cap
        conn.execute(
            """
            UPDATE courses
            SET name = %s, note = %s, new_energy = %s, review_energy = %s, review_default_test = %s,
                daily_minutes_cap = %s
            WHERE id = %s
            """,
            (
                merged["name"],
                merged["note"],
                merged.get("new_energy") or 30,
                merged.get("review_energy") or 30,
                bool(merged.get("review_default_test")),
                int(merged.get("daily_minutes_cap") or 0),
                course_id,
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM courses WHERE id = %s", (course_id,)).fetchone()
        owner_id = int(updated["user_id"])
        today = sm2.today_text()
        progress = _attach_time_cap(
            conn,
            updated,
            owner_id,
            today,
            _course_today_progress(conn, updated, owner_id, today),
        )
        return serialize_course(
            updated,
            _course_item_count(conn, course_id),
            published_count=_matching_published_count(conn, updated),
            progress=progress,
            week=_course_week_brief(conn, course_id, owner_id, today),
        )


@app.delete("/api/courses/{course_id}")
def delete_course(course_id: int, user=Depends(current_user)):
    with connect() as conn:
        course = _accessible_course(conn, course_id, user)
        owner_id = int(course["user_id"])
        conn.execute(
            "DELETE FROM review_log WHERE user_id = %s AND course_id = %s",
            (owner_id, course_id),
        )
        conn.execute(
            "DELETE FROM review_state WHERE user_id = %s AND course_id = %s",
            (owner_id, course_id),
        )
        conn.execute("DELETE FROM courses WHERE id = %s", (course_id,))
        conn.commit()
    return {"ok": True}


@app.post("/api/courses/{course_id}/sync")
def sync_course(course_id: int, user=Depends(current_user)):
    with connect() as conn:
        course = _accessible_course(conn, course_id, user)
        kinds = decode_filters(course.get("kinds"), KINDS)
        levels = decode_filters(course.get("levels"), LEVELS)
        if not kinds or not levels:
            raise HTTPException(status_code=400, detail="旧课程没有筛选条件，请新建课程后再同步")
        added = _sync_course_items(conn, course)
        conn.commit()
        count = _course_item_count(conn, course_id)
        result = serialize_course(course, count, published_count=_matching_published_count(conn, course))
        result["added"] = added
        return result


@app.get("/api/courses/{course_id}/today")
def today_queue(course_id: int, mode: str | None = None, wrongBook: int = 0, user=Depends(current_user)):
    if is_parent(user):
        raise HTTPException(status_code=403, detail="请让孩子打开今日默写")
    today = sm2.today_text()
    use_wrong = bool(wrongBook)
    with connect() as conn:
        course = _accessible_course(conn, course_id, user, student_only=True)
        owner_id = int(course["user_id"])
        _ensure_default_synced(conn, course)
        points, logs, planned = _plan_course_today(conn, course, owner_id, today)
        progress = _attach_time_cap(
            conn,
            course,
            owner_id,
            today,
            build_progress(planned, logs, item_count=len(points)),
        )
        if use_wrong:
            wrong_ids = {row["id"] for row in _wrong_book_rows(conn, course_id, owner_id)}
            selected = [row for row in points if row["id"] in wrong_ids]
            planned = _plan_wrong_book(selected)
    suggested = "test" if use_wrong else resolve_default_mode(planned, _course_review_pref(course))
    active = "test" if use_wrong else (normalize_mode(mode) if mode else suggested)
    planned = apply_today_mode(planned, active)
    items = []
    hide_source = active == "test"
    for entry in flatten_today_groups(planned["groups"]):
        qtype = entry["row"].get("question_type") or "dictation"
        extra = {
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
            "role": entry.get("role") or "new",
            "mode": active,
            "entryKey": entry["row"].get("entry_key") or "",
            "lemma": entry["row"].get("lemma") or "",
            "questionType": qtype,
            "audience": entry["row"].get("audience") or "all",
            "options": parse_options(entry["row"].get("options")),
        }
        show_answer = active == "recite" or (qtype == "recite" and active != "test")
        if show_answer:
            extra["answer"] = entry["row"].get("answer") or extra.get("lemma") or ""
            extra["lines"] = answer_lines(extra["answer"])
        item = serialize_point(entry["row"], extra)
        if hide_source:
            item["source"] = ""
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
        "itemCount": len(points),
        "courseName": course.get("name") or "",
        "isDefault": _is_default_course(course),
        "mode": active,
        "defaultMode": suggested,
        "reviewDefaultTest": _course_review_pref(course),
        "energyCharged": False if use_wrong else planned.get("energyCharged", True),
        "modes": list(MODE_OPTIONS),
        "progress": progress,
        "wrongBook": use_wrong,
        "dailyMinutesCap": int(course.get("daily_minutes_cap") or 0),
    }


@app.get("/api/courses/{course_id}/plan")
def course_plan(course_id: int, user=Depends(current_user)):
    with connect() as conn:
        course = _accessible_course(conn, course_id, user)
        _ensure_default_synced(conn, course)
        points = _course_plan_points(conn, course_id)
    plan = plan_course_days(points, course.get("new_energy") or 30, course.get("review_energy") or 30)
    plan["course"] = serialize_course(course, len(points))
    return plan


@app.post("/api/courses/{course_id}/review")
def review_point(course_id: int, body: ReviewBody, user=Depends(current_user)):
    if is_parent(user):
        raise HTTPException(status_code=403, detail="请让孩子打开今日默写")
    today = sm2.today_text()
    mode = normalize_mode(body.mode)
    with connect() as conn:
        course = _accessible_course(conn, course_id, user, student_only=True)
        _own_course(conn, course_id, course["user_id"])
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
        prev_state = {
            "n": point["n"],
            "ef": point["ef"],
            "interval": point["interval"],
            "lapses": point["lapses"],
        }
        if body.reveal:
            result = grade_card(point, "", reveal=True)
        else:
            result = grade_card(point, body.answer, reveal=False)
        outcome = review_outcome(mode, result, body.reveal)
        if not outcome["ok"]:
            raise HTTPException(status_code=400, detail=outcome["error"])
        result["quality"] = outcome["quality"]
        result["correct"] = outcome["correct"]
        next_state = prev_state
        if outcome["update_sm2"]:
            next_state = sm2.schedule(prev_state, result["quality"], today)
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
    result["lines"] = answer_lines(point["answer"])
    result["state"] = next_state
    result["isNew"] = is_new
    result["mode"] = mode
    result["updateSm2"] = outcome["update_sm2"]
    result["revealed"] = bool(body.reveal)
    result["feedback"] = kid_feedback(
        mode,
        result,
        revealed=bool(body.reveal),
        update_sm2=outcome["update_sm2"],
    )
    return result


@app.get("/api/courses/{course_id}/stats")
def course_stats(course_id: int, user=Depends(current_user)):
    today = sm2.today_text()
    with connect() as conn:
        course = _accessible_course(conn, course_id, user)
        owner_id = int(course["user_id"])
        _ensure_default_synced(conn, course)
        rows = conn.execute(
            """
            SELECT p.id, p.kind, p.level, p.grade, p.prompt, p.source, p.entry_key, p.lemma, p.question_type,
                   s.n, s.interval, s.due, s.lapses, s.last,
                   COALESCE(SUM(CASE WHEN l.is_new THEN 1 ELSE 0 END), 0) AS study_count,
                   COALESCE(SUM(CASE WHEN NOT l.is_new THEN 1 ELSE 0 END), 0) AS review_count,
                   COALESCE(SUM(CASE WHEN l.correct THEN 0 ELSE 1 END), 0) AS error_count,
                   COALESCE((
                       SELECT COUNT(DISTINCT l2.course_id)
                       FROM review_log l2
                       JOIN knowledge_published p2 ON p2.id = l2.point_id
                       WHERE l2.user_id = %s
                         AND p.entry_key <> ''
                         AND p2.entry_key = p.entry_key
                   ), 0) AS pass_count
            FROM course_items i
            JOIN knowledge_published p ON p.id = i.point_id
            LEFT JOIN review_state s
                ON s.point_id = p.id AND s.user_id = %s AND s.course_id = %s
            LEFT JOIN review_log l
                ON l.point_id = p.id AND l.user_id = %s AND l.course_id = %s
            WHERE i.course_id = %s
            GROUP BY p.id, p.kind, p.level, p.grade, p.prompt, p.source, p.entry_key, p.lemma, p.question_type,
                     s.n, s.interval, s.due, s.lapses, s.last, i.sort
            ORDER BY i.sort, p.id
            """,
            (owner_id, owner_id, course_id, owner_id, course_id, course_id),
        ).fetchall()
        points, logs, planned = _plan_course_today(conn, course, owner_id, today)
        week = _course_week_brief(conn, course_id, owner_id, today)
        wrong_rows = _wrong_book_rows(conn, course_id, owner_id)
        items = []
        for row in rows:
            item = dict(row)
            item["mastered"] = sm2.is_mastered(row)
            item["passCount"] = int(item.get("pass_count") or 0)
            items.append(item)
        mastery = mastery_counts(items)
        progress = build_progress(
            planned,
            logs,
            item_count=len(points),
            mastered=mastery["mastered"],
            total=mastery["total"],
        )
        if not progress["weakKinds"]:
            progress = dict(progress)
            progress["weakKinds"] = mastery["weakKinds"]
            progress["summary"] = parent_copy(
                progress["status"],
                progress["todayPracticed"],
                progress["todayAccuracy"],
                progress["weakKinds"],
                progress["remainingNewEnergy"],
                progress["remainingReviewEnergy"],
                mastered=mastery["mastered"],
                total=mastery["total"],
            )
        progress = _attach_time_cap(conn, course, owner_id, today, progress)
    return {
        "items": items,
        "today": progress,
        "mastery": mastery,
        "week": week,
        "wrongBook": _wrong_book_items(wrong_rows),
        "summary": progress["summary"],
        "courseName": course.get("name") or "",
        "reviewDefaultTest": _course_review_pref(course),
        "dailyMinutesCap": int(course.get("daily_minutes_cap") or 0),
        "canDrill": is_student(user) and int(user["id"]) == owner_id,
    }


@app.get("/api/courses/{course_id}/week")
def course_week(course_id: int, user=Depends(current_user)):
    today = sm2.today_text()
    with connect() as conn:
        course = _accessible_course(conn, course_id, user)
        return _course_week_brief(conn, course_id, int(course["user_id"]), today)


@app.get("/api/courses/{course_id}/wrong-book")
def course_wrong_book(course_id: int, user=Depends(current_user)):
    with connect() as conn:
        course = _accessible_course(conn, course_id, user)
        owner_id = int(course["user_id"])
        items = _wrong_book_items(_wrong_book_rows(conn, course_id, owner_id))
    return {
        "items": items,
        "courseName": course.get("name") or "",
        "canDrill": is_student(user) and int(user["id"]) == owner_id,
        "summary": (
            "最近容易错的有 %s 题，适合再练一遍。" % len(items)
            if items
            else "最近没有记下的错题。先去今日默写，写错过的会收在这里。"
        ),
    }


@app.post("/api/courses/{course_id}/study-time")
def add_study_time(course_id: int, body: StudyTimeBody, user=Depends(current_user)):
    if is_parent(user):
        raise HTTPException(status_code=403, detail="请让孩子打开今日默写")
    seconds = max(0, min(int(body.seconds or 0), 3600))
    today = sm2.today_text()
    with connect() as conn:
        course = _accessible_course(conn, course_id, user, student_only=True)
        if seconds:
            conn.execute(
                """
                INSERT INTO study_time (user_id, course_id, day, seconds)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, course_id, day) DO UPDATE SET
                    seconds = study_time.seconds + EXCLUDED.seconds
                """,
                (user["id"], course_id, today, seconds),
            )
            conn.commit()
        progress = _attach_time_cap(
            conn,
            course,
            user["id"],
            today,
            {"todayMinutes": 0},
        )
    return progress


@app.get("/api/library/coverage")
def library_coverage(user=Depends(current_user)):
    if is_parent(user):
        raise HTTPException(status_code=403, detail="覆盖页是给孩子看词库用的")
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM knowledge_published").fetchone()["n"]
        entry_count = conn.execute(
            """
            SELECT COUNT(DISTINCT CASE WHEN entry_key <> '' THEN entry_key ELSE 'id:' || id::text END) AS n
            FROM knowledge_published
            """
        ).fetchone()["n"]
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
        studied_entries = conn.execute(
            """
            SELECT COUNT(DISTINCT CASE WHEN p.entry_key <> '' THEN p.entry_key ELSE 'id:' || p.id::text END) AS n
            FROM review_log l
            JOIN knowledge_published p ON p.id = l.point_id
            WHERE l.user_id = %s
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
                   COUNT(DISTINCT CASE WHEN p.entry_key <> '' THEN p.entry_key ELSE 'id:' || p.id::text END) AS entries,
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
                   COUNT(DISTINCT CASE WHEN p.entry_key <> '' THEN p.entry_key ELSE 'id:' || p.id::text END) AS entries,
                   COUNT(DISTINCT CASE WHEN c.user_id = %s THEN i.point_id END) AS in_course
            FROM knowledge_published p
            LEFT JOIN course_items i ON i.point_id = p.id
            LEFT JOIN courses c ON c.id = i.course_id
            GROUP BY COALESCE(NULLIF(p.grade, ''), '未分年级')
            ORDER BY grade
            """,
            (user["id"],),
        ).fetchall()
        by_entry_grade = conn.execute(
            """
            SELECT g.grade,
                   COUNT(DISTINCT g.entry_key) AS entries,
                   COUNT(DISTINCT p.id) AS total,
                   COUNT(DISTINCT CASE WHEN c.user_id = %s THEN i.point_id END) AS in_course
            FROM knowledge_entry_grade g
            LEFT JOIN knowledge_published p ON p.entry_key = g.entry_key
            LEFT JOIN course_items i ON i.point_id = p.id
            LEFT JOIN courses c ON c.id = i.course_id
            GROUP BY g.grade
            ORDER BY g.grade
            """,
            (user["id"],),
        ).fetchall()
    return {
        "total": total,
        "entryCount": entry_count,
        "inCourse": in_course,
        "studied": studied,
        "studiedEntries": studied_entries,
        "mastered": mastered,
        "byKind": by_kind,
        "byGrade": by_grade,
        "byEntryGrade": by_entry_grade,
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
        "entryKey": point.get("entry_key") or "",
        "lemma": point.get("lemma") or "",
        "questionType": point.get("question_type") or "dictation",
        "audience": point.get("audience") or "all",
        "energy": point_energy(point),
    }
    if extra:
        data.update(extra)
    return data
