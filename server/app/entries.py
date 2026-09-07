"""词条（唯一 ID）与多张学习卡片：出题类型、受众、派生卡。"""
from __future__ import annotations

import hashlib
import json
import re

from .grade import normalize

QUESTION_TYPES = ("dictation", "recite", "char_judge", "meaning_choice")
QUESTION_TYPE_LABEL = {
    "dictation": "默写",
    "recite": "背诵",
    "char_judge": "字对错",
    "meaning_choice": "理解意思",
}
AUDIENCES = ("all", "lower", "upper")
AUDIENCE_LABEL = {
    "all": "全年级",
    "lower": "低年级",
    "upper": "高年级",
}
GRADE_ORDER = (
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
LEVEL_ORDER = ("L1", "L2", "L3", "L4")
LOWER_GRADES = {"一年级上", "一年级下", "二年级上", "二年级下"}
UPPER_GRADES = {"四年级上", "四年级下", "五年级上", "五年级下", "六年级上", "六年级下"}
MID_GRADES = {"三年级上", "三年级下"}
SOLO_KINDS = {"poem", "wenyan"}
HINT_MARKERS = ("形容", "比喻", "描写", "意思", "指", "表示")
SUFFIX_HINT = re.compile(r"（四字）$|（成语）$|（词语）$")
CONFUSABLES = {
    "己": "已",
    "已": "己",
    "未": "末",
    "末": "未",
    "土": "士",
    "士": "土",
    "入": "人",
    "人": "入",
    "天": "夭",
    "大": "太",
    "太": "大",
    "干": "千",
    "千": "干",
    "辩": "辨",
    "辨": "辩",
    "即": "既",
    "既": "即",
    "侯": "候",
    "候": "侯",
    "蓝": "篮",
    "篮": "蓝",
    "厉": "历",
    "历": "厉",
    "坐": "座",
    "座": "坐",
    "象": "像",
    "像": "象",
    "做": "作",
    "作": "做",
    "那": "哪",
    "哪": "那",
    "到": "道",
    "道": "到",
    "必": "心",
    "心": "必",
    "成": "城",
    "城": "成",
    "不": "步",
    "无": "天",
    "有": "友",
    "言": "信",
    "信": "言",
    "清": "青",
    "青": "清",
    "秀": "绣",
    "自": "字",
    "语": "悟",
    "春": "椿",
    "回": "徊",
    "大": "太",
    "地": "第",
    "万": "方",
    "物": "勿",
    "复": "覆",
    "苏": "酥",
}
GENERIC_HINTS = ("形容情况很好", "形容心情不好", "做事很认真", "景色很美丽")


def normalize_question_type(value):
    text = str(value or "").strip()
    return text if text in QUESTION_TYPES else "dictation"


def normalize_audience(value):
    text = str(value or "").strip()
    return text if text in AUDIENCES else "all"


def encode_options(value):
    if value is None or value == "":
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    return text


def parse_options(value):
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"display": text}
    if isinstance(data, (dict, list)):
        return data
    return {}


def stable_int(text):
    digest = hashlib.sha1(str(text or "").encode("utf-8")).hexdigest()[:8]
    return int(digest, 16)


def make_entry_key(kind, lemma, fallback=""):
    kind = str(kind or "").strip()
    lemma = str(lemma or "").strip()
    fallback = str(fallback or "").strip()
    if kind in SOLO_KINDS and fallback:
        return fallback
    compact = normalize(lemma) or lemma
    if kind and compact:
        return f"{kind}:{compact}"
    return fallback


def lemma_of(point):
    text = str((point or {}).get("lemma") or "").strip()
    if text:
        return text
    qtype = normalize_question_type((point or {}).get("question_type"))
    answer = str((point or {}).get("answer") or "").strip()
    if qtype in {"char_judge", "meaning_choice"}:
        return ""
    return answer


def meaning_hint(point):
    prompt = SUFFIX_HINT.sub("", str((point or {}).get("prompt") or "")).strip()
    return prompt


def looks_like_meaning(point):
    hint = meaning_hint(point)
    if len(hint) < 4:
        return False
    return any(marker in hint for marker in HINT_MARKERS) or "（四字）" in str((point or {}).get("prompt") or "")


def split_labels(text):
    items = []
    for raw in str(text or "").replace("，", ";").replace(",", ";").split(";"):
        item = raw.strip()
        if item and item not in items:
            items.append(item)
    return items


def merge_labels(old, extra, order=None):
    items = split_labels(old)
    for item in split_labels(extra):
        if item not in items:
            items.append(item)
    if order:
        rank = {name: index for index, name in enumerate(order)}
        items.sort(key=lambda name: (rank.get(name, len(rank)), name))
    return items


def join_labels(items):
    return ";".join(item for item in items if item)


def card_rank(row, selected_grades=None):
    selected = {str(item) for item in (selected_grades or []) if item}
    grade = str((row or {}).get("grade") or "")
    if selected:
        grade_score = 2 if grade in selected else (1 if grade else 0)
    else:
        grade_score = 1 if grade else 0
    level = str((row or {}).get("level") or "")
    level_score = LEVEL_ORDER.index(level) if level in LEVEL_ORDER else len(LEVEL_ORDER)
    try:
        row_id = int((row or {}).get("id") or 0)
    except (TypeError, ValueError):
        row_id = 0
    return (-grade_score, level_score, row_id)


def pick_course_cards(rows, grades=None):
    selected = [str(item) for item in (grades or []) if item]
    best = {}
    for row in rows or []:
        entry_key = str(row.get("entry_key") or "") or ("id:" + str(row.get("id") or ""))
        qtype = normalize_question_type(row.get("question_type"))
        key = (entry_key, qtype)
        current = best.get(key)
        if current is None or card_rank(row, selected) < card_rank(current, selected):
            best[key] = row
    return sorted(
        best.values(),
        key=lambda row: (
            str(row.get("grade") or ""),
            str(row.get("kind") or ""),
            str(row.get("entry_key") or ""),
            str(row.get("question_type") or ""),
            row.get("id") or 0,
        ),
    )


def audiences_for_grades(grades):
    selected = {str(item) for item in (grades or []) if item}
    if not selected:
        return None
    wanted = {"all"}
    if selected & LOWER_GRADES or selected & MID_GRADES:
        wanted.add("lower")
    if selected & UPPER_GRADES or selected & MID_GRADES:
        wanted.add("upper")
    return wanted


def mutate_lemma(text):
    source = str(text or "")
    chars = list(source)
    if not chars:
        return source + "甲"
    index = stable_int(source) % len(chars)
    current = chars[index]
    replacement = CONFUSABLES.get(current)
    if not replacement or replacement == current:
        for extra in "甲乙丙丁戊己庚辛":
            if extra not in source:
                replacement = extra
                break
        else:
            replacement = "甲"
    chars[index] = replacement
    mutated = "".join(chars)
    if mutated == source:
        return source[:-1] + "甲" if len(source) > 1 else source + "乙"
    return mutated


def fill_entry_fields(point):
    if not isinstance(point, dict):
        return point
    qtype = normalize_question_type(point.get("question_type"))
    audience = normalize_audience(point.get("audience"))
    key = str(point.get("key") or point.get("point_key") or "").strip()
    kind = point.get("kind") or ""
    lemma = lemma_of(point)
    if qtype == "recite" and not lemma:
        lemma = str(point.get("answer") or "").strip()
    if qtype == "dictation" and not lemma:
        lemma = str(point.get("answer") or "").strip()
    entry_key = str(point.get("entry_key") or "").strip() or make_entry_key(kind, lemma, key)
    point["question_type"] = qtype
    point["audience"] = audience
    point["lemma"] = lemma
    point["entry_key"] = entry_key
    point["options"] = encode_options(point.get("options"))
    if entry_key:
        point["group"] = entry_key
        point["group_key"] = entry_key
    if not str(point.get("sub_group") or "").strip():
        point["sub_group"] = qtype
        point["sub_group_key"] = qtype
    return point


def make_char_judge_card(base):
    lemma = str(base.get("lemma") or base.get("answer") or "").strip()
    key = str(base.get("key") or base.get("point_key") or "").strip()
    wrong = mutate_lemma(lemma)
    use_wrong = stable_int(lemma + ":judge") % 2 == 1
    display = wrong if use_wrong else lemma
    card = dict(base)
    card["key"] = f"{key}:char_judge" if key else ""
    card["question_type"] = "char_judge"
    card["audience"] = "lower"
    card["lemma"] = lemma
    card["prompt"] = "下面的写法对不对？"
    card["answer"] = "错" if use_wrong else "对"
    card["options"] = {"display": display}
    card["sub_group"] = "char_judge"
    return fill_entry_fields(card)


def _choice_pool(points):
    hints = []
    seen = set()
    for point in points or []:
        hint = meaning_hint(point)
        if len(hint) < 4 or hint in seen:
            continue
        if normalize_question_type(point.get("question_type")) in {"char_judge", "meaning_choice"}:
            continue
        seen.add(hint)
        hints.append(hint)
    return hints


def make_meaning_card(base, pool):
    lemma = str(base.get("lemma") or base.get("answer") or "").strip()
    key = str(base.get("key") or base.get("point_key") or "").strip()
    correct = meaning_hint(base) or "请选择正确的意思"
    others = [item for item in pool if item != correct]
    others.sort(key=lambda item: stable_int(lemma + item))
    distractors = others[:3]
    pad = 0
    while len(distractors) < 3:
        extra = GENERIC_HINTS[pad % len(GENERIC_HINTS)]
        if extra != correct and extra not in distractors:
            distractors.append(extra)
        pad += 1
    choices = [correct] + distractors
    choices.sort(key=lambda item: stable_int(lemma + ":choice:" + item))
    card = dict(base)
    card["key"] = f"{key}:meaning_choice" if key else ""
    card["question_type"] = "meaning_choice"
    card["audience"] = "upper"
    card["lemma"] = lemma
    card["prompt"] = f"「{lemma}」的意思是？"
    card["answer"] = correct
    card["options"] = {"choices": choices}
    card["sub_group"] = "meaning_choice"
    return fill_entry_fields(card)


def maybe_expand_pack_cards(points):
    rows = [dict(item) for item in (points or []) if isinstance(item, dict)]
    if any(normalize_question_type(item.get("question_type")) in {"char_judge", "meaning_choice"} for item in rows):
        return [fill_entry_fields(item) for item in rows]
    pool = _choice_pool(rows)
    expanded = []
    for item in rows:
        point = fill_entry_fields(dict(item))
        kind = point.get("kind") or ""
        if kind in SOLO_KINDS or kind == "idiom":
            point["question_type"] = "recite"
        point["audience"] = "all"
        point = fill_entry_fields(point)
        expanded.append(point)
        lemma = point.get("lemma") or ""
        compact = normalize(lemma)
        if kind == "idiom":
            continue
        if kind in {"zi", "saying"} and 1 <= len(compact) <= 8:
            expanded.append(make_char_judge_card(point))
        if kind == "saying" and looks_like_meaning(point):
            expanded.append(make_meaning_card(point, pool))
    return expanded
