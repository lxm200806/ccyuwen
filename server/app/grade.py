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
