"""今日默写三种学习模式：学习 / 测试 / 背诵。"""
import re

MODES = ("learn", "test", "recite")
DEFAULT_MODE = "learn"
LEARN_REVEAL_QUALITY = 3
MODE_OPTIONS = (
    {"id": "learn", "label": "学习", "hint": "先练会"},
    {"id": "test", "label": "测试", "hint": "考考你"},
    {"id": "recite", "label": "背诵", "hint": "读出来"},
)
LINE_SPLIT = re.compile(r"(?<=[。！？；!\?;\n])")


def normalize_mode(value, default=DEFAULT_MODE):
    text = str(value or "").strip().lower()
    if text in MODES:
        return text
    aliases = {"学习": "learn", "测试": "test", "背诵": "recite"}
    return aliases.get(str(value or "").strip(), default if default in MODES else DEFAULT_MODE)


def default_study_mode(planned):
    """到期复习卡排在今日队列前面时，默认测试；否则默认学习。"""
    groups = list((planned or {}).get("groups") or [])
    if groups and groups[0].get("role") == "review":
        return "test"
    review_energy = int((planned or {}).get("reviewEnergy") or 0)
    new_energy = int((planned or {}).get("newEnergy") or 0)
    if review_energy and not new_energy:
        return "test"
    return "learn"


def has_review_work(planned):
    groups = list((planned or {}).get("groups") or [])
    if any(group.get("role") == "review" for group in groups):
        return True
    return int((planned or {}).get("reviewEnergy") or 0) > 0


def resolve_default_mode(planned, review_default_test=False):
    """家长勾选「到期复习默认用测试」时，只要还有复习卡就默认测试。"""
    if review_default_test and has_review_work(planned):
        return "test"
    return default_study_mode(planned)


def groups_for_mode(groups, mode):
    """测试优先只收复习卡；没有复习卡时回退到当日全部卡。学习/背诵用当日完整计划。"""
    mode = normalize_mode(mode)
    rows = list(groups or [])
    if mode != "test":
        return rows
    review = [group for group in rows if group.get("role") == "review"]
    return review or rows


def apply_today_mode(planned, mode):
    """按模式裁剪今日学习卡，并调整展示用的能量。背诵不消耗新学/复习能量。"""
    planned = dict(planned or {})
    active = normalize_mode(mode)
    groups = groups_for_mode(planned.get("groups") or [], active)
    new_energy = sum(int(group.get("energy") or 0) for group in groups if group.get("role") != "review")
    review_energy = sum(int(group.get("energy") or 0) for group in groups if group.get("role") == "review")
    charged = active != "recite"
    planned["groups"] = groups
    planned["tasks"] = len(groups)
    planned["cards"] = sum(len(group.get("rows") or []) for group in groups)
    planned["newEnergy"] = new_energy if charged else 0
    planned["reviewEnergy"] = review_energy if charged else 0
    planned["mode"] = active
    planned["energyCharged"] = charged
    return planned


def answer_lines(answer):
    text = str(answer or "").strip()
    if not text:
        return []
    parts = [item.strip() for item in LINE_SPLIT.split(text) if item and item.strip()]
    return parts or [text]


def reveal_allowed(mode):
    return normalize_mode(mode) == "learn"


def review_outcome(mode, grade_result, revealed=False):
    """把判分结果收成该模式的 SM-2 质量。

    学习 + 看答案：记 quality=3（模糊），过关但降熟练度，不记 lapse。
    测试：禁止看答案；提交按原判分严格更新 SM-2。
    背诵：不写 SM-2。
    """
    active = normalize_mode(mode)
    result = grade_result if isinstance(grade_result, dict) else {}
    quality = int(result.get("quality") or 1)
    correct = bool(result.get("correct"))
    if active == "test" and revealed:
        return {
            "ok": False,
            "error": "测试模式不能看答案",
            "mode": active,
            "update_sm2": False,
        }
    if active == "recite":
        return {
            "ok": True,
            "mode": active,
            "quality": quality,
            "correct": correct,
            "update_sm2": False,
            "revealed": bool(revealed),
        }
    if active == "learn" and revealed:
        return {
            "ok": True,
            "mode": active,
            "quality": LEARN_REVEAL_QUALITY,
            "correct": False,
            "update_sm2": True,
            "revealed": True,
        }
    return {
        "ok": True,
        "mode": active,
        "quality": quality,
        "correct": correct,
        "update_sm2": True,
        "revealed": bool(revealed),
    }
