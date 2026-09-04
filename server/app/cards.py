"""卡片校验与 CSV/JSON 导入解析。"""
import csv
import hashlib
import io
import json
import re

from .grade import normalize
from . import sm2

KINDS = ("poem", "wenyan", "idiom", "saying", "sentence", "zi")
LEVELS = ("L1", "L2", "L3", "L4")
KIND_LABEL = {
    "poem": "古诗",
    "wenyan": "文言文",
    "idiom": "词语",
    "saying": "俗语名句",
    "sentence": "优美句子",
    "zi": "易错字",
}
GRADES = (
    "一年级上",
    "一年级下",
    "二年级上",
    "二年级下",
    "三年级上",
    "三年级下",
    "四年级上",
    "四年级下",
    "五年级上",
    "五年级下",
    "六年级上",
    "六年级下",
)
PAGE_DEFAULT = 200
PAGE_MAX = 500
SOLO_KINDS = {"poem", "wenyan"}
DEFAULT_NEW_ENERGY = 30
DEFAULT_REVIEW_ENERGY = 30
ENERGY_MIN = 8
ENERGY_MAX = 120
PLAN_QUALITY = 5
PLAN_MAX_DAYS = 240


def encode_filters(values, allowed):
    return ",".join(item for item in values if item in allowed)


def decode_filters(text, allowed):
    return [item for item in str(text or "").split(",") if item in allowed]


# None = no filter; 0 = only rows with source_resource_id IS NULL; >0 = that resource.
UNLINKED_RESOURCE_TOKENS = {"0", "unlinked", "none"}
ALL_RESOURCE_TOKENS = {"", "all", "*", "undefined", "null"}


def parse_resource_filter(resource_id=None, unlinked=False):
    if unlinked:
        return 0
    text = "" if resource_id is None else str(resource_id).strip()
    lowered = text.lower()
    if lowered in ALL_RESOURCE_TOKENS:
        return None
    if lowered in UNLINKED_RESOURCE_TOKENS:
        return 0
    try:
        value = int(text)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def page_args(limit, offset):
    try:
        safe_limit = int(limit)
    except (TypeError, ValueError):
        safe_limit = PAGE_DEFAULT
    try:
        safe_offset = int(offset)
    except (TypeError, ValueError):
        safe_offset = 0
    return min(max(safe_limit, 1), PAGE_MAX), max(safe_offset, 0)


def validate_card(kind, prompt, answer):
    if kind not in KINDS:
        return "类型无效，仅支持 poem / wenyan / idiom / saying / sentence / zi"
    if not str(prompt or "").strip() or not str(answer or "").strip():
        return "提示和答案必填"
    compact = normalize(answer)
    if kind == "zi" and len(compact) != 1:
        return "易错字答案必须是一个字"
    if kind == "idiom" and (len(compact) < 3 or len(compact) > 8):
        return "词语过长，请拆成一条"
    if kind == "saying" and len(compact) > 40:
        return "俗语名句过长，请拆成一条"
    if kind == "poem" and len(compact) > 80:
        return "古诗卡片过大，请拆成名句或短篇"
    if kind == "wenyan" and len(compact) > 160:
        return "文言文卡片过大，请拆成一段"
    if kind == "sentence" and len(compact) > 120:
        return "优美句子过长，请拆成一句"
    return None


def normalize_grade(value):
    text = str(value or "").strip()
    return text if text in GRADES else ""


def normalize_point(item):
    if not isinstance(item, dict):
        return None
    kind = item.get("kind") if item.get("kind") in KINDS else "poem"
    level = item.get("level") if item.get("level") in LEVELS else "L1"
    prompt = str(item.get("prompt") or "").strip()
    answer = str(item.get("answer") or "").strip()
    error = validate_card(kind, prompt, answer)
    if error:
        return None
    point = {
        "key": str(item.get("key") or item.get("point_key") or "").strip(),
        "kind": kind,
        "level": level,
        "grade": normalize_grade(item.get("grade")),
        "prompt": prompt,
        "answer": answer,
        "tags": str(item.get("tags") or "").strip(),
        "source": str(item.get("source") or "").strip(),
        "group": str(item.get("group") or "").strip(),
        "sub_group": str(item.get("sub_group") or "").strip(),
    }
    return fill_group_fields(point)


def parse_import(text):
    raw = str(text or "").replace("\ufeff", "").strip()
    if not raw:
        return {"ok": [], "skip": 0}
    if raw[0] in "[{":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": [], "skip": 1}
        if isinstance(data, list):
            return collect_rows(data)
        if isinstance(data, dict) and isinstance(data.get("points"), list):
            return collect_rows(data["points"])
        return {"ok": [], "skip": 1}
    return collect_rows(parse_csv(raw))


def collect_rows(rows):
    if not isinstance(rows, list):
        return {"ok": [], "skip": 1}
    ok = []
    skip = 0
    for row in rows:
        point = normalize_point(row)
        if point:
            ok.append(point)
        else:
            skip += 1
    return {"ok": ok, "skip": skip}


def parse_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append({(key or "").strip(): (value or "").strip() for key, value in row.items()})
    return rows


CITATION_SUFFIX = re.compile(r"·《[^》]+》$")


def tag_theme(tags):
    parts = [item.strip() for item in str(tags or "").split(";") if item.strip()]
    return ";".join(parts[:2])


def module_source(source):
    return CITATION_SUFFIX.sub("", str(source or "").strip())


def derive_group_key(point):
    kind = point.get("kind")
    key = str(point.get("key") or point.get("point_key") or "").strip()
    if kind in SOLO_KINDS:
        if key:
            return key
        payload = "|".join(
            [
                str(point.get("grade") or ""),
                str(kind or ""),
                str(point.get("prompt") or ""),
                str(point.get("answer") or ""),
            ]
        )
        return "solo-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    payload = "|".join(
        [
            str(point.get("grade") or ""),
            str(kind or ""),
            module_source(point.get("source")),
            tag_theme(point.get("tags")),
        ]
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return "g1-" + digest


def fill_group_fields(point):
    if not isinstance(point, dict):
        return point
    explicit_group = str(point.get("group") or "").strip()
    explicit_sub = str(point.get("sub_group") or "").strip()
    point["group_key"] = explicit_group or derive_group_key(point)
    point["sub_group_key"] = explicit_sub
    return point


def row_group_key(row):
    return str(row.get("group_key") or row.get("point_key") or row.get("id") or "")


def cluster_groups(rows):
    groups = []
    seen = {}
    for row in rows:
        key = row_group_key(row)
        if key not in seen:
            seen[key] = {"group_key": key, "rows": []}
            groups.append(seen[key])
        seen[key]["rows"].append(row)
    return groups


def parse_energy_limit(value, default=DEFAULT_NEW_ENERGY):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, ENERGY_MIN), ENERGY_MAX)


def energy_overflow(daily):
    return max(6, int(daily) // 5)


def point_energy(point):
    raw = point.get("energy")
    if raw is not None and str(raw).strip() != "":
        try:
            value = int(raw)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    kind = point.get("kind")
    tags = str(point.get("tags") or "")
    length = len(normalize(point.get("answer") or ""))
    if kind == "zi":
        return 1
    if kind == "idiom":
        return 4 if "成语" in tags else 2
    if kind == "saying":
        return 4 if length <= 16 else 8
    if kind == "sentence":
        return 8 if length <= 40 else 12
    if kind == "poem":
        if length <= 24:
            return 16
        if length <= 48:
            return 24
        return 32
    if kind == "wenyan":
        if length <= 40:
            return 24
        if length <= 80:
            return 32
        if length <= 120:
            return 64
        return 96
    return 4


def rows_energy(rows):
    return sum(point_energy(row) for row in rows)


def session_days(energy, daily):
    limit = int(daily) + energy_overflow(daily)
    if energy <= limit:
        return 1
    return max(2, (energy + int(daily) - 1) // int(daily))


def make_session(group, rows, part=1, parts=1):
    first = rows[0] if rows else {}
    source = str(first.get("source") or "").strip()
    return {
        "group_key": group["group_key"],
        "rows": list(rows),
        "energy": rows_energy(rows),
        "part": part,
        "parts": parts,
        "kind": first.get("kind") or "",
        "grade": first.get("grade") or "",
        "source": source,
        "title": source or str(first.get("prompt") or "学习卡"),
    }


def expand_sessions(groups, daily):
    sessions = []
    limit = int(daily) + energy_overflow(daily)
    for group in groups:
        rows = list(group["rows"])
        energy = rows_energy(rows)
        days = session_days(energy, daily)
        if days == 1:
            sessions.append(make_session(group, rows))
            continue
        if len(rows) == 1:
            for part in range(1, days + 1):
                session = make_session(group, rows, part, days)
                session["energy"] = min(int(daily), energy - (part - 1) * int(daily)) or int(daily)
                sessions.append(session)
            continue
        chunks = []
        chunk = []
        chunk_energy = 0
        for row in rows:
            cost = point_energy(row)
            if chunk and chunk_energy + cost > limit:
                chunks.append(chunk)
                chunk = []
                chunk_energy = 0
            chunk.append(row)
            chunk_energy += cost
        if chunk:
            chunks.append(chunk)
        parts = max(len(chunks), 1)
        for index, piece in enumerate(chunks, start=1):
            sessions.append(make_session(group, piece, index, parts))
    return sessions


def pack_one_day(sessions, daily):
    limit = int(daily) + energy_overflow(daily)
    picked = []
    used = 0
    for session in sessions:
        cost = session["energy"]
        if picked and used + cost > limit:
            break
        picked.append(session)
        used += cost
    return picked, used


def pack_all_days(sessions, daily):
    remaining = list(sessions)
    days = []
    while remaining:
        picked, used = pack_one_day(remaining, daily)
        if not picked:
            picked = [remaining[0]]
            used = remaining[0]["energy"]
        days.append({"sessions": picked, "energy": used})
        remaining = remaining[len(picked) :]
    return days


def row_id(row):
    if row.get("id") is not None:
        return row["id"]
    return row.get("point_key") or row.get("key") or id(row)


def session_completes_points(session):
    if len(session.get("rows") or []) == 1 and int(session.get("parts") or 1) > 1:
        return int(session.get("part") or 1) >= int(session.get("parts") or 1)
    return True


def serialize_plan_days(days):
    result = []
    for index, day in enumerate(days, start=1):
        cards = []
        point_count = 0
        new_points = 0
        review_points = 0
        for session in day["sessions"]:
            count = len(session["rows"])
            point_count += count
            role = session.get("role") or "new"
            if role == "review":
                review_points += count
            else:
                new_points += count
            cards.append(
                {
                    "title": session["title"],
                    "groupKey": session["group_key"],
                    "kind": session["kind"],
                    "grade": session["grade"],
                    "source": session["source"],
                    "energy": session["energy"],
                    "pointCount": count,
                    "part": session["part"],
                    "parts": session["parts"],
                    "role": role,
                    "prompts": [str(row.get("prompt") or "") for row in session["rows"][:8]],
                }
            )
        new_energy = day.get("new_energy")
        review_energy = day.get("review_energy")
        if new_energy is None:
            new_energy = sum(item["energy"] for item in cards if item["role"] != "review")
        if review_energy is None:
            review_energy = sum(item["energy"] for item in cards if item["role"] == "review")
        if review_energy and new_energy:
            mode = "mixed"
        elif review_energy:
            mode = "review"
        else:
            mode = "new"
        result.append(
            {
                "day": day.get("day") or index,
                "mode": mode,
                "energy": day.get("energy") if day.get("energy") is not None else new_energy + review_energy,
                "newEnergy": new_energy,
                "reviewEnergy": review_energy,
                "pointCount": point_count,
                "newPointCount": new_points,
                "reviewPointCount": review_points,
                "cardCount": len(day["sessions"]),
                "cards": cards,
            }
        )
    return result


def plan_course_days(rows, new_energy=DEFAULT_NEW_ENERGY, review_energy=DEFAULT_REVIEW_ENERGY):
    new_budget = parse_energy_limit(new_energy, DEFAULT_NEW_ENERGY)
    review_budget = parse_energy_limit(review_energy, DEFAULT_REVIEW_ENERGY)
    remaining_new = expand_sessions(cluster_groups(rows), new_budget)
    states = {}
    days = []
    new_day_count = 0
    start = "2000-01-01"
    for offset in range(PLAN_MAX_DAYS):
        today = sm2.add_days(start, offset)
        due_rows = []
        for row in rows:
            state = states.get(row_id(row))
            if not state or sm2.is_mastered(state):
                continue
            if str(state.get("due") or "") <= today:
                due_rows.append(row)
        review_sessions = expand_sessions(cluster_groups(due_rows), review_budget)
        for session in review_sessions:
            session["role"] = "review"
        review_today, review_used = pack_one_day(review_sessions, review_budget)
        new_today, new_used = [], 0
        if remaining_new:
            remaining_new = [
                session
                for session in remaining_new
                if not all(row_id(row) in states for row in session["rows"])
            ]
            new_today, new_used = pack_one_day(remaining_new, new_budget)
            remaining_new = remaining_new[len(new_today) :]
            for session in new_today:
                session["role"] = "new"
        if not review_today and not new_today:
            if remaining_new:
                continue
            if any(state and not sm2.is_mastered(state) for state in states.values()):
                continue
            break
        for session in review_today + new_today:
            if session.get("role") == "new" and not session_completes_points(session):
                continue
            for row in session["rows"]:
                key = row_id(row)
                states[key] = sm2.schedule(states.get(key), PLAN_QUALITY, today)
        if new_today:
            new_day_count += 1
        days.append(
            {
                "day": offset + 1,
                "sessions": review_today + new_today,
                "energy": review_used + new_used,
                "new_energy": new_used,
                "review_energy": review_used,
            }
        )
    return {
        "newEnergy": new_budget,
        "reviewEnergy": review_budget,
        "groupCount": len(cluster_groups(rows)),
        "pointCount": len(rows),
        "totalEnergy": rows_energy(rows),
        "dayCount": len(days),
        "newDayCount": new_day_count,
        "calendarDays": days[-1]["day"] if days else 0,
        "days": serialize_plan_days(days),
    }


def plan_today_groups(rows, failed_ids, today, new_energy=DEFAULT_NEW_ENERGY, review_energy=DEFAULT_REVIEW_ENERGY):
    new_budget = parse_energy_limit(new_energy, DEFAULT_NEW_ENERGY)
    review_budget = parse_energy_limit(review_energy, DEFAULT_REVIEW_ENERGY)
    due_rows, failed_rows, fresh_rows = [], [], []
    for row in rows:
        if not row.get("last"):
            fresh_rows.append(row)
        elif str(row.get("due") or "") <= today:
            due_rows.append(row)
        elif row.get("id") in failed_ids:
            failed_rows.append(row)
    review_sessions = expand_sessions(cluster_groups(due_rows) + cluster_groups(failed_rows), review_budget)
    fresh_sessions = expand_sessions(cluster_groups(fresh_rows), new_budget)
    review_today, review_used = pack_one_day(review_sessions, review_budget)
    fresh_today, fresh_used = pack_one_day(fresh_sessions, new_budget)
    picked = review_today + fresh_today
    return {
        "groups": picked,
        "due": len(cluster_groups(due_rows)),
        "failed": len(cluster_groups(failed_rows)),
        "fresh": len(cluster_groups(fresh_rows)),
        "tasks": len(picked),
        "cards": sum(len(session["rows"]) for session in picked),
        "newEnergy": fresh_used,
        "reviewEnergy": review_used,
        "newBudget": new_budget,
        "reviewBudget": review_budget,
    }


def flatten_today_groups(groups):
    items = []
    task_count = len(groups)
    for task_index, group in enumerate(groups, start=1):
        size = len(group["rows"])
        for group_index, row in enumerate(group["rows"], start=1):
            items.append(
                {
                    "row": row,
                    "group_key": group["group_key"],
                    "group_size": size,
                    "group_index": group_index,
                    "task_index": task_index,
                    "task_count": task_count,
                    "energy": point_energy(row),
                    "group_energy": group.get("energy") or rows_energy(group["rows"]),
                    "part": group.get("part") or 1,
                    "parts": group.get("parts") or 1,
                    "title": group.get("title") or "",
                }
            )
    return items
