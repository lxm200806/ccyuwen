"""今日进度、家长摘要、孩子反馈文案。不改 SM-2。"""
from .cards import KIND_LABEL

STATUS_EMPTY = "empty"
STATUS_DONE = "done"
STATUS_IDLE = "idle"
STATUS_REMAINING = "remaining"


def trailing_streak(logs):
    streak = 0
    for row in reversed(list(logs or [])):
        if not row.get("correct"):
            break
        streak += 1
    return streak


def accuracy_percent(attempts, correct):
    if attempts <= 0:
        return None
    return round(100 * correct / attempts)


def weak_kind_rows(counts, limit=3):
    rows = []
    for kind, stats in (counts or {}).items():
        errors = int(stats.get("errors") or 0)
        if errors <= 0:
            continue
        rows.append(
            {
                "kind": kind,
                "label": KIND_LABEL.get(kind, kind),
                "errors": errors,
                "attempts": int(stats.get("attempts") or 0),
            }
        )
    rows.sort(key=lambda item: (-item["errors"], item["label"]))
    return rows[:limit]


def remaining_energy_text(new_energy, review_energy):
    new_energy = int(new_energy or 0)
    review_energy = int(review_energy or 0)
    parts = []
    if new_energy:
        parts.append("新学 %s 能" % new_energy)
    if review_energy:
        parts.append("复习 %s 能" % review_energy)
    if not parts:
        return ""
    return "、".join(parts)


def progress_status(item_count, remaining_cards, practiced):
    if int(item_count or 0) <= 0:
        return STATUS_EMPTY
    if int(remaining_cards or 0) > 0:
        return STATUS_REMAINING
    if int(practiced or 0) > 0:
        return STATUS_DONE
    return STATUS_IDLE


def student_copy(status, new_energy, review_energy):
    remaining = remaining_energy_text(new_energy, review_energy)
    if status == STATUS_EMPTY:
        return "这门课还没有知识点", "请先同步新词，或去组课生成一份。"
    if status == STATUS_DONE:
        return "今天练完了", "新学和复习都完成了，明天再来。真好。"
    if status == STATUS_IDLE:
        return "今天没有要练的", "没有到期复习，也没有排进今日的新学卡。明天再来，或打开学习计划看看后面几天。"
    if remaining:
        return "还差" + remaining, "写完这些就收工。先复习到期的，再学新的。"
    return "还差几条", "继续写，写完就收工。"


def parent_copy(status, practiced, accuracy, weak_kinds, new_energy, review_energy, mastered=None, total=None):
    remaining = remaining_energy_text(new_energy, review_energy)
    weak_text = "、".join(item["label"] for item in (weak_kinds or [])[:3])
    if status == STATUS_EMPTY:
        return "这门课还没有知识点，组课或同步后再看掌握情况。"
    if practiced <= 0 and status == STATUS_IDLE:
        sentence = "今天还没开始练，也没有到期复习或新学任务。"
    elif practiced <= 0:
        sentence = "今天还没开始练。"
        if remaining:
            sentence += "还差" + remaining + "。"
    elif status == STATUS_DONE:
        sentence = "今天练完了。共练 %s 条" % practiced
        if accuracy is not None:
            sentence += "，正确率 %s%%" % accuracy
        sentence += "。"
    else:
        sentence = "今天已练 %s 条" % practiced
        if accuracy is not None:
            sentence += "，正确率 %s%%" % accuracy
        if remaining:
            sentence += "。还差" + remaining + "。"
        else:
            sentence += "。"
    if weak_text and practiced:
        sentence += "相对容易错的是" + weak_text + "。"
    if total:
        mastered_n = int(mastered or 0)
        sentence += "课内已掌握 %s / %s 条。" % (mastered_n, int(total))
    return sentence


def kid_feedback(mode, grade_result, revealed=False, update_sm2=True):
    result = grade_result if isinstance(grade_result, dict) else {}
    chars = list(result.get("chars") or [])
    wrong = []
    seen = set()
    for item in chars:
        if item.get("ok"):
            continue
        ch = str(item.get("char") or "")
        if not ch or ch in seen:
            continue
        seen.add(ch)
        wrong.append(ch)
    correct = bool(result.get("correct"))
    quality = int(result.get("quality") or 1)
    will_retry = bool(update_sm2) and quality < 3 and not revealed

    if mode == "recite":
        if correct:
            return {
                "title": "读得对",
                "hint": "背诵只练读和听，不改下次出现的日子。",
                "next": "继续下一题。",
                "wrongChars": [],
            }
        return {
            "title": "再读一读",
            "hint": "对照原文读顺就好，不必着急手写。",
            "next": "继续下一题。",
            "wrongChars": wrong,
        }
    if revealed:
        return {
            "title": "看过答案了",
            "hint": "先记住标准答案。这次记成「模糊」，比写错轻，下次还会再见面。",
            "next": "下一题接着练。",
            "wrongChars": [],
        }
    if correct:
        return {
            "title": "全对！",
            "hint": "写得很稳。",
            "next": "下一题接着练。",
            "wrongChars": [],
        }
    if quality == 3:
        hint = "大体对了，标红的字再看一眼。"
        if wrong:
            hint = "大体对了，这几个字再记一下：" + "、".join(wrong) + "。"
        return {
            "title": "差不多对了",
            "hint": hint,
            "next": "下一题接着练。",
            "wrongChars": wrong,
        }
    hint = "对照标准答案，把不一样的地方再写一遍。"
    if wrong:
        hint = "不一样的字：" + "、".join(wrong) + "。看清楚再写。"
    return {
        "title": "这题先记下",
        "hint": hint,
        "next": "这题等会儿还会再练一次。" if will_retry else "下一题接着练。",
        "wrongChars": wrong,
    }


def summarize_logs(logs):
    rows = list(logs or [])
    attempts = len(rows)
    correct = sum(1 for row in rows if row.get("correct"))
    practiced_ids = {row.get("point_id") for row in rows if row.get("point_id") is not None}
    done_ids = {
        row.get("point_id")
        for row in rows
        if row.get("point_id") is not None and int(row.get("quality") or 0) >= 3
    }
    kind_counts = {}
    for row in rows:
        kind = row.get("kind") or ""
        if not kind:
            continue
        stats = kind_counts.setdefault(kind, {"attempts": 0, "errors": 0})
        stats["attempts"] += 1
        if not row.get("correct"):
            stats["errors"] += 1
    return {
        "todayAttempts": attempts,
        "todayCorrect": correct,
        "todayPracticed": len(practiced_ids),
        "todayDoneCount": len(done_ids),
        "todayStreak": trailing_streak(rows),
        "todayAccuracy": accuracy_percent(attempts, correct),
        "weakKinds": weak_kind_rows(kind_counts),
    }


def build_progress(planned, logs, item_count=0, mastered=None, total=None):
    planned = planned or {}
    log_stats = summarize_logs(logs)
    remaining_cards = int(planned.get("cards") or 0)
    remaining_tasks = int(planned.get("tasks") or 0)
    new_energy = int(planned.get("newEnergy") or 0)
    review_energy = int(planned.get("reviewEnergy") or 0)
    new_budget = int(planned.get("newBudget") or 30)
    review_budget = int(planned.get("reviewBudget") or 30)
    status = progress_status(item_count, remaining_cards, log_stats["todayPracticed"])
    title, hint = student_copy(status, new_energy, review_energy)
    summary = parent_copy(
        status,
        log_stats["todayPracticed"],
        log_stats["todayAccuracy"],
        log_stats["weakKinds"],
        new_energy,
        review_energy,
        mastered=mastered,
        total=total,
    )
    energy_filled = remaining_cards <= 0 and int(item_count or 0) > 0
    return {
        "status": status,
        "title": title,
        "hint": hint,
        "summary": summary,
        "todayAttempts": log_stats["todayAttempts"],
        "todayCorrect": log_stats["todayCorrect"],
        "todayPracticed": log_stats["todayPracticed"],
        "todayDoneCount": log_stats["todayDoneCount"],
        "todayStreak": log_stats["todayStreak"],
        "todayAccuracy": log_stats["todayAccuracy"],
        "weakKinds": log_stats["weakKinds"],
        "remainingNewEnergy": new_energy,
        "remainingReviewEnergy": review_energy,
        "remainingCards": remaining_cards,
        "remainingTasks": remaining_tasks,
        "newBudget": new_budget,
        "reviewBudget": review_budget,
        "todayDone": status == STATUS_DONE or (energy_filled and log_stats["todayPracticed"] > 0),
        "energyFilled": energy_filled,
    }


def mastery_counts(items):
    total = len(items or [])
    mastered = 0
    learning = 0
    unseen = 0
    kind_counts = {}
    for item in items or []:
        kind = item.get("kind") or ""
        if kind:
            stats = kind_counts.setdefault(kind, {"attempts": 0, "errors": 0})
            stats["attempts"] += int(item.get("study_count") or 0) + int(item.get("review_count") or 0)
            stats["errors"] += int(item.get("error_count") or 0)
        if item.get("mastered"):
            mastered += 1
        elif item.get("last"):
            learning += 1
        else:
            unseen += 1
    return {
        "total": total,
        "mastered": mastered,
        "learning": learning,
        "unseen": unseen,
        "weakKinds": weak_kind_rows(kind_counts),
    }
