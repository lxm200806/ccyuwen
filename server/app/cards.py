"""卡片校验与 CSV/JSON 导入解析。"""
import csv
import io
import json

from .grade import normalize

KINDS = ("poem", "idiom", "zi")
LEVELS = ("L1", "L2", "L3", "L4")
KIND_LABEL = {"poem": "古诗", "idiom": "成语", "zi": "易错字"}


def validate_card(kind, prompt, answer):
    if kind not in KINDS:
        return "类型无效，仅支持 poem / idiom / zi"
    if not str(prompt or "").strip() or not str(answer or "").strip():
        return "提示和答案必填"
    compact = normalize(answer)
    if kind == "zi" and len(compact) != 1:
        return "易错字答案必须是一个字"
    if kind == "idiom" and (len(compact) < 3 or len(compact) > 8):
        return "成语过长，请拆成一条"
    if kind == "poem" and len(compact) > 80:
        return "古诗卡片过大，请拆成名句或短篇"
    return None


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
    return {
        "kind": kind,
        "level": level,
        "prompt": prompt,
        "answer": answer,
        "tags": str(item.get("tags") or "").strip(),
        "source": str(item.get("source") or "").strip(),
    }


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
