"""默写判分，与 js/grade.js 对齐。"""
import re

PUNCT = re.compile(r"[\s，。！？、；：,.!?;:'\"“”‘’《》【】（）()\[\]—…·]")


def normalize(text):
    if text is None:
        return ""
    return PUNCT.sub("", str(text))


def levenshtein(left, right):
    a = "" if left is None else str(left)
    b = "" if right is None else str(right)
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def diff_chars(typed, expected):
    answer = normalize(expected)
    compact = normalize(typed)
    return [{"char": ch, "ok": compact[i] == ch if i < len(compact) else False} for i, ch in enumerate(answer)]


def grade_answer(user_input, expected):
    typed = normalize(user_input)
    answer = normalize(expected)
    if not answer:
        return {"quality": 1, "ratio": 0, "correct": False, "chars": []}
    if not typed:
        return {"quality": 1, "ratio": 0, "correct": False, "chars": diff_chars("", answer)}
    if typed == answer:
        return {"quality": 5, "ratio": 1, "correct": True, "chars": diff_chars(typed, answer)}
    distance = levenshtein(typed, answer)
    ratio = 1 - distance / max(len(typed), len(answer))
    safe_ratio = max(0, round(ratio, 2))
    quality = 1
    if safe_ratio >= 0.95:
        quality = 5
    elif safe_ratio >= 0.8:
        quality = 3
    return {
        "quality": quality,
        "ratio": safe_ratio,
        "correct": quality == 5,
        "chars": diff_chars(typed, answer),
    }


def normalize_judge(value):
    text = normalize(value)
    aliases = {"对": "对", "正确": "对", "true": "对", "1": "对", "yes": "对", "错": "错", "错误": "错", "false": "错", "0": "错", "no": "错"}
    return aliases.get(text.lower(), text)


def grade_char_judge(user_input, expected):
    typed = normalize_judge(user_input)
    answer = normalize_judge(expected)
    correct = bool(typed) and typed == answer
    return {
        "quality": 5 if correct else 1,
        "ratio": 1 if correct else 0,
        "correct": correct,
        "chars": [],
    }


def grade_choice(user_input, expected):
    typed = normalize(user_input)
    answer = normalize(expected)
    if not answer:
        return {"quality": 1, "ratio": 0, "correct": False, "chars": []}
    correct = bool(typed) and typed == answer
    return {
        "quality": 5 if correct else 1,
        "ratio": 1 if correct else 0,
        "correct": correct,
        "chars": [],
    }


def grade_card(point, user_input, reveal=False):
    from .entries import normalize_question_type

    qtype = normalize_question_type((point or {}).get("question_type"))
    expected = (point or {}).get("answer") or ""
    if reveal:
        if qtype == "char_judge":
            return grade_char_judge("", expected)
        if qtype == "meaning_choice":
            return grade_choice("", expected)
        return grade_answer("", expected)
    if qtype == "char_judge":
        return grade_char_judge(user_input, expected)
    if qtype == "meaning_choice":
        return grade_choice(user_input, expected)
    return grade_answer(user_input, expected)
