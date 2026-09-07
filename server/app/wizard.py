"""年级向导：按册推荐类型、级别和约 15 分钟的每日能量。"""
from .cards import GRADES, KIND_LABEL, LEVELS

KIND_ORDER = ("zi", "idiom", "poem", "saying", "wenyan", "sentence")

# 约 15 分钟语文：低年级少类型、能量偏小；高年级补文言文和更高级别。
WIZARD_BY_BAND = {
    "一年级": {
        "kinds": ["zi", "idiom", "poem"],
        "levels": ["L1"],
        "newEnergy": 16,
        "reviewEnergy": 16,
        "minutes": 15,
        "blurb": "先认字、词语和短诗，每天大约一刻钟。",
    },
    "二年级": {
        "kinds": ["zi", "idiom", "poem", "saying"],
        "levels": ["L1", "L2"],
        "newEnergy": 18,
        "reviewEnergy": 16,
        "minutes": 15,
        "blurb": "字词和古诗为主，加上一点俗语，仍按一刻钟来。",
    },
    "三年级": {
        "kinds": ["zi", "idiom", "poem", "saying", "wenyan"],
        "levels": ["L1", "L2"],
        "newEnergy": 20,
        "reviewEnergy": 18,
        "minutes": 15,
        "blurb": "开始接触短文言，词语和古诗一起练。",
    },
    "四年级": {
        "kinds": ["zi", "idiom", "poem", "saying", "wenyan", "sentence"],
        "levels": ["L1", "L2", "L3"],
        "newEnergy": 22,
        "reviewEnergy": 20,
        "minutes": 15,
        "blurb": "课内必背加上拓展，文言文和句子都收一点。",
    },
    "五年级": {
        "kinds": ["zi", "idiom", "poem", "saying", "wenyan", "sentence"],
        "levels": ["L1", "L2", "L3"],
        "newEnergy": 24,
        "reviewEnergy": 22,
        "minutes": 15,
        "blurb": "覆盖课内到小升初常见篇目，仍按一刻钟收工。",
    },
    "六年级": {
        "kinds": ["zi", "idiom", "poem", "saying", "wenyan", "sentence"],
        "levels": ["L1", "L2", "L3", "L4"],
        "newEnergy": 24,
        "reviewEnergy": 24,
        "minutes": 15,
        "blurb": "冲刺小升初，类型齐、级别齐，每天还是大约一刻钟。",
    },
}


def grade_band(grade):
    text = str(grade or "")
    for band in ("六年级", "五年级", "四年级", "三年级", "二年级", "一年级"):
        if text.startswith(band):
            return band
    return ""


def wizard_plan(grade):
    if grade not in GRADES:
        return None
    spec = WIZARD_BY_BAND[grade_band(grade)]
    kinds = [item for item in spec["kinds"] if item in KIND_ORDER]
    levels = [item for item in spec["levels"] if item in LEVELS]
    return {
        "grade": grade,
        "kinds": kinds,
        "kindLabels": [KIND_LABEL[item] for item in kinds],
        "levels": levels,
        "newEnergy": spec["newEnergy"],
        "reviewEnergy": spec["reviewEnergy"],
        "minutes": spec["minutes"],
        "name": grade + "默写",
        "note": spec["blurb"],
        "blurb": spec["blurb"],
    }


def list_wizard_grades():
    return [wizard_plan(grade) for grade in GRADES]
