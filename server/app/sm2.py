"""SM-2 间隔重复，与 js/sm2.js 对齐。"""
from datetime import date, datetime, timedelta

MIN_EASE = 1.3
FIRST_INTERVAL = 1
SECOND_INTERVAL = 6


def parse_day(day_text):
    if not day_text:
        return None
    try:
        return datetime.strptime(str(day_text)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def format_day(value):
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return ""
    return value.isoformat()


def today_text():
    return date.today().isoformat()


def add_days(day_text, day_count):
    parsed = parse_day(day_text)
    if parsed is None:
        return ""
    return (parsed + timedelta(days=int(day_count))).isoformat()


def schedule(state, quality, today=None):
    safe_today = today or today_text()
    prev = state if isinstance(state, dict) else {}
    n = int(prev.get("n") or 0)
    ef = float(prev.get("ef") or 2.5)
    interval = int(prev.get("interval") or 0)
    lapses = int(prev.get("lapses") or 0)
    try:
        score = float(quality)
    except (TypeError, ValueError):
        score = 0

    if score != score or score < 3:
        n = 0
        interval = FIRST_INTERVAL
        lapses += 1
    else:
        if n == 0:
            interval = FIRST_INTERVAL
        elif n == 1:
            interval = SECOND_INTERVAL
        else:
            interval = max(1, round(interval * ef))
        n += 1
        gap = 5 - score
        ef = ef + (0.1 - gap * (0.08 + gap * 0.02))
        if ef < MIN_EASE:
            ef = MIN_EASE

    return {
        "n": n,
        "ef": round(ef, 2),
        "interval": interval,
        "due": add_days(safe_today, interval),
        "lapses": lapses,
        "last": safe_today,
    }


def is_mastered(state):
    if not state:
        return False
    return int(state.get("interval") or 0) >= 21 or int(state.get("n") or 0) >= 5
