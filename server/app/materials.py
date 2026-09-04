"""原始教材备份，以及从材料包同步知识点。"""
import hashlib
import json
import os
from pathlib import Path

from .cards import fill_group_fields, parse_import
from .grade3a_points import GRADE3A_POINTS
from .high_grade_points import (
    GRADE3X_POINTS,
    GRADE4S_POINTS,
    GRADE4X_POINTS,
    GRADE5S_POINTS,
    GRADE5X_POINTS,
    GRADE6S_POINTS,
    GRADE6X_POINTS,
)
from .low_grade_points import GRADE1S_POINTS, GRADE1X_POINTS, GRADE2S_POINTS, GRADE2X_POINTS

PACKS = (
    {
        "slug": "grade1-shang",
        "title": "部编版一年级上册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编一年级上册.json",
        "md_name": "部编一年级上册.md",
        "bundled": "grade1-shang.md",
        "points": GRADE1S_POINTS,
    },
    {
        "slug": "grade1-xia",
        "title": "部编版一年级下册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编一年级下册.json",
        "md_name": "部编一年级下册.md",
        "bundled": "grade1-xia.md",
        "points": GRADE1X_POINTS,
    },
    {
        "slug": "grade2-shang",
        "title": "部编版二年级上册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编二年级上册.json",
        "md_name": "部编二年级上册.md",
        "bundled": "grade2-shang.md",
        "points": GRADE2S_POINTS,
    },
    {
        "slug": "grade2-xia",
        "title": "部编版二年级下册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编二年级下册.json",
        "md_name": "部编二年级下册.md",
        "bundled": "grade2-xia.md",
        "points": GRADE2X_POINTS,
    },
    {
        "slug": "grade3-shang",
        "title": "部编版三年级上册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编三年级上册.json",
        "md_name": "部编三年级上册.md",
        "bundled": "grade3-shang.md",
        "points": GRADE3A_POINTS,
    },
    {
        "slug": "grade3-xia",
        "title": "部编版三年级下册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编三年级下册.json",
        "md_name": "部编三年级下册.md",
        "bundled": "grade3-xia.md",
        "points": GRADE3X_POINTS,
    },
    {
        "slug": "grade4-shang",
        "title": "部编版四年级上册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编四年级上册.json",
        "md_name": "部编四年级上册.md",
        "bundled": "grade4-shang.md",
        "points": GRADE4S_POINTS,
    },
    {
        "slug": "grade4-xia",
        "title": "部编版四年级下册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编四年级下册.json",
        "md_name": "部编四年级下册.md",
        "bundled": "grade4-xia.md",
        "points": GRADE4X_POINTS,
    },
    {
        "slug": "grade5-shang",
        "title": "部编版五年级上册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编五年级上册.json",
        "md_name": "部编五年级上册.md",
        "bundled": "grade5-shang.md",
        "points": GRADE5S_POINTS,
    },
    {
        "slug": "grade5-xia",
        "title": "部编版五年级下册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编五年级下册.json",
        "md_name": "部编五年级下册.md",
        "bundled": "grade5-xia.md",
        "points": GRADE5X_POINTS,
    },
    {
        "slug": "grade6-shang",
        "title": "部编版六年级上册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编六年级上册.json",
        "md_name": "部编六年级上册.md",
        "bundled": "grade6-shang.md",
        "points": GRADE6S_POINTS,
    },
    {
        "slug": "grade6-xia",
        "title": "部编版六年级下册｜必背古诗 + 日积月累 + 课文优美句子",
        "json_name": "部编六年级下册.json",
        "md_name": "部编六年级下册.md",
        "bundled": "grade6-xia.md",
        "points": GRADE6X_POINTS,
    },
)

_DEFAULT = next(item for item in PACKS if item["slug"] == "grade3-shang")
SLUG = _DEFAULT["slug"]
TITLE = _DEFAULT["title"]
JSON_NAME = _DEFAULT["json_name"]
MD_NAME = _DEFAULT["md_name"]


def data_root():
    return Path(os.environ.get("DATA_ROOT", str(Path(__file__).resolve().parents[1] / "data")))


def raw_root():
    configured = os.environ.get("RAW_ROOT", "").strip()
    if configured:
        return Path(configured)
    repo_raw = Path(__file__).resolve().parents[2] / "raw"
    if repo_raw.is_dir():
        return repo_raw
    return Path("/app/raw")


def materials_dir():
    return Path(__file__).resolve().parent / "materials"


def find_pack(slug):
    text = str(slug or "").strip()
    if text.endswith("-original"):
        text = text[: -len("-original")]
    for pack in PACKS:
        if pack["slug"] == text:
            return pack
    return None


def bundled_md(pack=None):
    spec = pack or _DEFAULT
    return materials_dir() / spec["bundled"]


def read_original(pack=None):
    spec = pack or _DEFAULT
    for path in (raw_root() / spec["md_name"], bundled_md(spec)):
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return ""


def normalize_original(text):
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def pack_fingerprint(pack):
    payload = {
        "original": normalize_original(pack.get("original") or ""),
        "points": [
            {
                "key": str(item.get("key") or ""),
                "kind": str(item.get("kind") or ""),
                "level": str(item.get("level") or ""),
                "grade": str(item.get("grade") or ""),
                "prompt": str(item.get("prompt") or ""),
                "answer": str(item.get("answer") or ""),
                "tags": str(item.get("tags") or ""),
                "source": str(item.get("source") or ""),
            }
            for item in (pack.get("points") or [])
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_version(value):
    try:
        version = int(value or 0)
    except (TypeError, ValueError):
        return 1
    return version if version > 0 else 1


def next_version(old_version, old_hash, new_hash):
    version = parse_version(old_version)
    if old_hash and new_hash and old_hash != new_hash:
        return version + 1
    return version


def sync_state(file_hash, synced_hash):
    if not synced_hash:
        return "pending"
    if synced_hash == file_hash:
        return "synced"
    return "outdated"


def read_pack_file(path, pack=None):
    spec = pack or _DEFAULT
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None
    parsed = parse_import(raw)
    original = str(data.get("original") or "")
    if not normalize_original(original):
        original = read_original(spec)
    loaded = {
        "slug": str(data.get("slug") or spec["slug"]),
        "title": str(data.get("title") or spec["title"]),
        "original": original,
        "points": parsed["ok"],
        "skip": parsed["skip"],
        "version": parse_version(data.get("version")),
    }
    loaded["contentHash"] = str(data.get("contentHash") or "") or pack_fingerprint(loaded)
    return loaded


def load_pack(pack=None):
    spec = pack or _DEFAULT
    json_path = raw_root() / spec["json_name"]
    original = read_original(spec)
    stored_version = 1
    stored_hash = ""
    if json_path.is_file():
        loaded = read_pack_file(json_path, spec)
        if loaded:
            stored_version = loaded.get("version") or 1
            stored_hash = str(loaded.get("contentHash") or "") or pack_fingerprint(loaded)
            if original:
                loaded["original"] = original
            loaded["contentHash"] = pack_fingerprint(loaded)
            loaded["version"] = next_version(stored_version, stored_hash, loaded["contentHash"])
            return loaded
    result = {
        "slug": spec["slug"],
        "title": spec["title"],
        "original": original,
        "points": [fill_group_fields(dict(item)) for item in spec["points"]],
        "skip": 0,
    }
    result["contentHash"] = pack_fingerprint(result)
    result["version"] = next_version(stored_version, stored_hash, result["contentHash"])
    return result


def dump_pack(pack):
    return json.dumps(
        {
            "slug": pack.get("slug") or SLUG,
            "title": pack.get("title") or TITLE,
            "version": parse_version(pack.get("version")),
            "contentHash": pack.get("contentHash") or pack_fingerprint(pack),
            "original": pack.get("original") or "",
            "points": pack.get("points") or [],
        },
        ensure_ascii=False,
        indent=2,
    )


def write_official_files(pack, spec=None):
    spec = spec or find_pack(pack.get("slug")) or _DEFAULT
    folder = data_root() / "official" / "bundled"
    folder.mkdir(parents=True, exist_ok=True)
    json_rel = (Path("official") / "bundled" / spec["json_name"]).as_posix()
    md_rel = (Path("official") / "bundled" / spec["md_name"]).as_posix()
    (data_root() / json_rel).write_text(dump_pack(pack), encoding="utf-8")
    (data_root() / md_rel).write_text(pack.get("original") or "", encoding="utf-8")
    raw_dir = raw_root()
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / spec["json_name"]).write_text(dump_pack(pack), encoding="utf-8")
        if pack.get("original") and not (raw_dir / spec["md_name"]).is_file():
            (raw_dir / spec["md_name"]).write_text(pack["original"], encoding="utf-8")
        bundled = bundled_md(spec)
        if pack.get("original") and not bundled.is_file():
            bundled.parent.mkdir(parents=True, exist_ok=True)
            bundled.write_text(pack["original"], encoding="utf-8")
    except OSError:
        pass
    return json_rel, md_rel


def ensure_resource(cur, rel_path, filename, slug, mime, version=0, content_hash=""):
    cur.execute(
        "SELECT * FROM resources WHERE owner_type = 'official' AND slug = %s",
        (slug,),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE resources
            SET path = %s, filename = %s, mime = %s, status = 'extracted'
            WHERE id = %s
            """,
            (rel_path, filename, mime, row["id"]),
        )
        return row["id"]
    cur.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")
    admin = cur.fetchone()
    admin_id = admin["id"] if admin else None
    cur.execute(
        """
        INSERT INTO resources (owner_type, owner_id, path, filename, mime, status, uploaded_by, slug,
            synced_version, synced_hash)
        VALUES ('official', NULL, %s, %s, %s, 'extracted', %s, %s, %s, %s)
        RETURNING id
        """,
        (rel_path, filename, mime, admin_id, slug, version, content_hash),
    )
    return cur.fetchone()["id"]


def mark_synced(cur, resource_id, version, content_hash):
    cur.execute(
        """
        UPDATE resources
        SET status = 'extracted', synced_version = %s, synced_hash = %s
        WHERE id = %s
        """,
        (parse_version(version), content_hash or "", resource_id),
    )


def point_unchanged(row, point, resource_id, key):
    return (
        row["kind"] == point["kind"]
        and row["level"] == point["level"]
        and (row.get("grade") or "") == (point.get("grade") or "")
        and row["prompt"] == point["prompt"]
        and row["answer"] == point["answer"]
        and (row.get("tags") or "") == (point.get("tags") or "")
        and (row.get("source") or "") == (point.get("source") or "")
        and (row.get("point_key") or "") == key
        and (row.get("group_key") or "") == (point.get("group_key") or "")
        and (row.get("sub_group_key") or "") == (point.get("sub_group_key") or "")
        and (row.get("source_resource_id") == resource_id or resource_id is None)
    )


def upsert_published(cur, point, resource_id=None, force=False):
    point = fill_group_fields(dict(point))
    key = str(point.get("key") or "").strip()
    existing = None
    if key:
        cur.execute("SELECT * FROM knowledge_published WHERE point_key = %s", (key,))
        existing = cur.fetchone()
    if not existing:
        cur.execute(
            "SELECT * FROM knowledge_published WHERE prompt = %s AND answer = %s",
            (point["prompt"], point["answer"]),
        )
        existing = cur.fetchone()
    fields = (
        point["kind"],
        point["level"],
        point.get("grade") or "",
        point["prompt"],
        point["answer"],
        point.get("tags") or "",
        point.get("source") or "",
        resource_id,
        key,
        point.get("group_key") or "",
        point.get("sub_group_key") or "",
    )
    if existing:
        if not force and point_unchanged(existing, point, resource_id, key):
            return existing["id"], "unchanged"
        cur.execute(
            """
            UPDATE knowledge_published
            SET kind=%s, level=%s, grade=%s, prompt=%s, answer=%s, tags=%s, source=%s,
                source_resource_id=%s, point_key=%s, group_key=%s, sub_group_key=%s, published_at=NOW()
            WHERE id=%s
            """,
            fields + (existing["id"],),
        )
        return existing["id"], "updated"
    cur.execute(
        """
        INSERT INTO knowledge_published
            (kind, level, grade, prompt, answer, tags, source, source_resource_id, point_key,
             group_key, sub_group_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        fields,
    )
    return cur.fetchone()["id"], "inserted"


def attach_default_course(cur, point_ids):
    cur.execute("SELECT id FROM courses WHERE name = %s", ("默认课程",))
    for course in cur.fetchall():
        cur.execute(
            "SELECT COALESCE(MAX(sort), -1) AS n FROM course_items WHERE course_id = %s",
            (course["id"],),
        )
        max_sort = cur.fetchone()["n"]
        cur.execute("SELECT point_id FROM course_items WHERE course_id = %s", (course["id"],))
        existing = {row["point_id"] for row in cur.fetchall()}
        for point_id in point_ids:
            if point_id in existing:
                continue
            max_sort += 1
            cur.execute(
                "INSERT INTO course_items (course_id, point_id, sort) VALUES (%s, %s, %s)",
                (course["id"], point_id, max_sort),
            )


def sync_pack(cur, spec, force=True):
    pack = load_pack(spec)
    json_rel, md_rel = write_official_files(pack, spec)
    json_id = ensure_resource(
        cur, json_rel, spec["json_name"], spec["slug"], "application/json",
        pack.get("version") or 1, pack.get("contentHash") or "",
    )
    ensure_resource(cur, md_rel, spec["md_name"], spec["slug"] + "-original", "text/markdown")
    inserted = 0
    updated = 0
    unchanged = 0
    ids = []
    for point in pack["points"]:
        point_id, status = upsert_published(cur, point, json_id, force=force)
        ids.append(point_id)
        if status == "inserted":
            inserted += 1
        elif status == "updated":
            updated += 1
        else:
            unchanged += 1
    attach_default_course(cur, ids)
    mark_synced(cur, json_id, pack.get("version") or 1, pack.get("contentHash") or "")
    return {
        "resourceId": json_id,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "skip": pack.get("skip") or 0,
        "total": len(pack["points"]),
        "title": pack.get("title") or spec["title"],
        "version": pack.get("version") or 1,
        "contentHash": pack.get("contentHash") or "",
        "syncState": "synced",
    }


def resource_synced_hash(cur, slug):
    cur.execute(
        "SELECT synced_hash, synced_version FROM resources WHERE owner_type = 'official' AND slug = %s",
        (slug,),
    )
    row = cur.fetchone()
    if not row:
        return "", 0
    return row.get("synced_hash") or "", int(row.get("synced_version") or 0)


def pack_status(cur, spec):
    pack = load_pack(spec)
    synced_hash, synced_version = resource_synced_hash(cur, spec["slug"])
    state = sync_state(pack.get("contentHash") or "", synced_hash)
    return {
        "slug": spec["slug"],
        "title": pack.get("title") or spec["title"],
        "version": pack.get("version") or 1,
        "contentHash": pack.get("contentHash") or "",
        "syncedVersion": synced_version,
        "syncedHash": synced_hash,
        "syncState": state,
        "pointCount": len(pack.get("points") or []),
    }


def decorate_resource(row, status_by_slug=None):
    data = dict(row)
    slug = str(data.get("slug") or "")
    spec = find_pack(slug)
    data["isPack"] = bool(spec) and not slug.endswith("-original")
    data["isOriginal"] = slug.endswith("-original")
    info = (status_by_slug or {}).get(spec["slug"] if spec else "")
    if data["isPack"] and info:
        data["version"] = info["version"]
        data["syncedVersion"] = info["syncedVersion"]
        data["syncState"] = info["syncState"]
        data["pointCount"] = info["pointCount"]
        data["title"] = info["title"]
    elif data["isPack"] and spec:
        data["version"] = int(data.get("synced_version") or 0)
        data["syncedVersion"] = int(data.get("synced_version") or 0)
        data["syncState"] = ""
        data["pointCount"] = 0
        data["title"] = spec["title"]
    else:
        data["version"] = int(data.get("synced_version") or 0)
        data["syncedVersion"] = int(data.get("synced_version") or 0)
        data["syncState"] = ""
        data["pointCount"] = 0
        data["title"] = data.get("filename") or ""
    return data


def summarize_sync(results, mode):
    return {
        "mode": mode,
        "packs": len(results),
        "synced": sum(1 for item in results if not item.get("skipped")),
        "skipped": sum(1 for item in results if item.get("skipped")),
        "inserted": sum(item.get("inserted") or 0 for item in results),
        "updated": sum(item.get("updated") or 0 for item in results),
        "unchanged": sum(item.get("unchanged") or 0 for item in results),
        "items": results,
    }


def sync_grade3a(cur):
    return sync_pack(cur, _DEFAULT, force=True)


def sync_all_official(cur, force=False):
    results = []
    for spec in PACKS:
        if not force:
            info = pack_status(cur, spec)
            if info["syncState"] == "synced":
                results.append(
                    {
                        "resourceId": None,
                        "inserted": 0,
                        "updated": 0,
                        "unchanged": info["pointCount"],
                        "skip": 0,
                        "total": info["pointCount"],
                        "title": info["title"],
                        "version": info["version"],
                        "contentHash": info["contentHash"],
                        "syncState": "synced",
                        "skipped": True,
                    }
                )
                continue
        results.append(sync_pack(cur, spec, force=force))
    return results
