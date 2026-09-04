#!/usr/bin/env python3
"""从教辅高频成语清单生成小学成语知识点（候选库全部收录）。

课内条目以 raw/idioms/textbook_by_grade.json 为准（统编 1–6 年级，
分日积月累 / 课文）。已有 point_key 按成语原文保留，避免同步时另插一条。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "raw" / "idioms"
SEED = OUT_DIR / "seed_all_candidates.txt"
TEXTBOOK = OUT_DIR / "textbook_by_grade.json"
PRINTABLE_MD = ROOT / "raw" / "小学成语.md"
XINHUA = Path("/tmp/idiom.json")
JSON_NAME = "小学成语.json"
CSV_NAME = "小学成语.csv"
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

THEME_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("春天", ("春", "莺", "柳绿", "花红", "复苏")),
    ("秋天", ("秋", "桂", "落叶", "硕果", "五谷")),
    ("冬天", ("雪", "冰", "寒", "霜")),
    ("夏天", ("炎", "暑", "汗", "烈日", "骄阳")),
    ("外貌", ("眉", "目秀", "貌", "衣冠", "鹤发", "容光", "仪表", "亭亭")),
    ("神态", ("目不", "目瞪", "神采", "垂头", "趾高", "眉开", "怒发", "和颜")),
    ("学习", ("学", "书", "读", "习", "问", "思", "勤", "卷", "笔", "课")),
    ("品质", ("诚", "信", "善", "勇", "公", "私", "廉", "谦", "俭", "忠")),
    ("场面", ("人山", "人海", "车水", "熙", "摩肩", "座无", "门庭", "热闹", "灯火")),
    ("写景", ("山", "水", "花", "云", "风", "雨", "月", "星", "峰", "湖", "波")),
    ("寓言", ("守株", "亡羊", "画蛇", "掩耳", "刻舟", "滥竽", "邯郸", "矛盾", "杞人", "井底", "狐假", "拔苗", "叶公", "南辕", "坐井", "塞翁", "愚公", "精卫", "黔驴", "买椟")),
    ("历史", ("卧薪", "三顾", "四面楚", "破釜", "背水", "纸上", "负荆", "完璧", "东山", "乐不思", "约法", "毛遂", "指鹿")),
    ("动物", ("狼", "虎", "龙", "凤", "鸡", "狗", "鱼", "鸟", "马", "鼠", "蛇", "蝉", "蜂", "鹤")),
    ("艺术", ("笔", "画龙", "妙笔", "栩栩", "惟妙", "巧夺", "行云", "天籁", "余音", "炉火", "出神")),
    ("心情", ("心花", "兴高", "欢天", "喜出", "心旷", "提心", "忐忑", "忧心", "愁眉", "灰心", "如愿")),
    ("时间", ("光阴", "日月如", "白驹", "稍纵", "昙花", "时不", "机不可", "争分", "夜以", "通宵")),
    ("数字", ("一", "三", "四", "五", "六", "七", "八", "九", "十", "百", "千", "万")),
]

AABB = re.compile(r"^(.)\1(.)\2$")
ABAC = re.compile(r"^(.).(.)\1.$")
AABC = re.compile(r"^(.)\1..$")
ABCC = re.compile(r"^..(.)\1$")


def load_xinhua() -> dict[str, dict]:
    if not XINHUA.exists():
        return {}
    rows = json.loads(XINHUA.read_text(encoding="utf-8"))
    return {r["word"]: r for r in rows if r.get("word")}


def load_textbook_blocks() -> list[dict]:
    data = json.loads(TEXTBOOK.read_text(encoding="utf-8"))
    return list(data.get("blocks") or [])


def load_textbook() -> dict[str, dict]:
    """word -> grade / section / source / tags / group (首次出现为准)."""
    info: dict[str, dict] = {}
    for block in load_textbook_blocks():
        grade = str(block.get("grade") or "").strip()
        section = str(block.get("section") or "").strip()
        if grade not in GRADE_ORDER or section not in {"日积月累", "课文"}:
            continue
        for raw in block.get("words") or []:
            word = str(raw or "").strip()
            if not re.fullmatch(r"[\u4e00-\u9fff]{3,8}", word):
                continue
            appearance = {"grade": grade, "section": section}
            row = info.setdefault(word, {"appearances": []})
            if appearance not in row["appearances"]:
                row["appearances"].append(appearance)

    for word, row in info.items():
        apps = sorted(
            row["appearances"],
            key=lambda item: (GRADE_ORDER.index(item["grade"]), 0 if item["section"] == "日积月累" else 1),
        )
        primary = apps[0]
        sources: list[str] = []
        sections: list[str] = []
        for item in apps:
            source = f"部编{item['grade']}册·{item['section']}"
            if source not in sources:
                sources.append(source)
            if item["section"] not in sections:
                sections.append(item["section"])
        row["grade"] = primary["grade"]
        row["section"] = primary["section"]
        row["source"] = "；".join(sources)
        row["tags"] = ";".join(["成语", *sections, "课内必背"])
        row["group"] = f"成语-{primary['grade']}-{primary['section']}"
        row["sub_group"] = primary["section"]
    return info


def load_existing_pack() -> list[dict]:
    path = OUT_DIR / JSON_NAME
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("points") or [])


def load_existing_keys() -> dict[str, str]:
    snapshot = OUT_DIR / "_keys_before.json"
    if snapshot.is_file():
        extra = json.loads(snapshot.read_text(encoding="utf-8"))
        keys: dict[str, str] = {}
        if isinstance(extra, dict):
            for answer, key in extra.items():
                word = str(answer or "").strip()
                kept = str(key or "").strip()
                if word and kept:
                    keys[word] = kept
        return keys
    keys = {}
    reserved: set[str] = set()
    for point in load_existing_pack():
        answer = str(point.get("answer") or "").strip()
        key = str(point.get("key") or "").strip()
        if not answer or not key or answer in keys or key in reserved:
            continue
        keys[answer] = key
        reserved.add(key)
    return keys


def assign_key(word: str, existing: dict[str, str], used: set[str], reserved: set[str]) -> str:
    old = existing.get(word, "")
    if old and old not in used:
        return old
    n = 1
    while True:
        candidate = f"idiom-tb-{n:04d}"
        if candidate not in used and candidate not in reserved:
            return candidate
        n += 1


def printable_markdown(blocks: list[dict]) -> str:
    by_grade: dict[str, dict[str, list[str]]] = {}
    for block in blocks:
        grade = str(block.get("grade") or "").strip()
        section = str(block.get("section") or "").strip()
        words = [str(w).strip() for w in (block.get("words") or []) if str(w).strip()]
        if grade and section and words:
            by_grade.setdefault(grade, {})[section] = words
    lines = [
        "# 统编版1‑6年级成语·纯打印版",
        "（分【日积月累】【课文成语】，无多余解释，可直接复制打印）",
        "",
    ]
    for grade in GRADE_ORDER:
        sections = by_grade.get(grade) or {}
        lines.append(f"## {grade}册")
        lines.append("【日积月累】")
        daily = sections.get("日积月累") or []
        lines.append("、".join(daily) if daily else "无成语")
        lines.append("【课文成语】")
        text = sections.get("课文") or []
        lines.append("、".join(text) if text else "无")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def simplify_explanation(text: str, word: str) -> str:
    raw = text or ""
    text = re.sub(r"[★☆].*$", "", raw)
    text = text.replace("～", "……")
    preferred = ""
    best_idx = -1
    for marker in ("比喻", "形容", "现多指", "后比喻", "现用来", "多指", "指"):
        idx = text.find(marker)
        if idx >= 0 and (best_idx < 0 or idx < best_idx):
            # Prefer earlier clause; skip late "有时也比喻个人的情况" style tails when an earlier 指/多指 exists
            best_idx = idx
            preferred = text[idx:]
    if preferred and "有时也" in preferred[:4]:
        # try earlier marker before this tail
        earlier = text[: best_idx]
        alt = -1
        alt_text = ""
        for marker in ("多指", "指", "形容", "比喻"):
            idx = earlier.find(marker)
            if idx >= 0 and (alt < 0 or idx < alt):
                alt = idx
                alt_text = earlier[idx:]
        if alt_text:
            preferred = alt_text
    if preferred:
        text = preferred
    else:
        parts = re.split(r"[。]", text)
        if len(parts) >= 2 and len(parts[0]) <= 20:
            text = "。".join(parts[1:])
    text = re.split(r"[。；;]", text)[0].strip()
    text = re.sub(r"^(指|形容|比喻|表示|现多指|后比喻|现用来)", "", text).strip(" ，,")
    text = re.sub(r"^[①②③④\d、．.]+", "", text)
    if len(text) > 24:
        text = text[:24].rstrip("，,的地得与和")
    if len(text) < 4:
        return ""
    # Reject leftover single-character dictionary glosses only.
    if re.fullmatch(r"[\u4e00-\u9fff]{1,3}", text):
        return ""
    return text


THEME_DEFAULT_HINT = {
    "春天": "描写春天的成语",
    "夏天": "描写夏天的成语",
    "秋天": "描写秋天的成语",
    "冬天": "描写冬天的成语",
    "外貌": "描写外貌的成语",
    "神态": "描写神态的成语",
    "学习": "与学习有关的成语",
    "品质": "描写品质的成语",
    "场面": "描写场面的成语",
    "写景": "描写景物的成语",
    "寓言": "出自寓言故事的成语",
    "历史": "出自历史故事的成语",
    "动物": "含有动物的成语",
    "艺术": "形容艺术水平的成语",
    "心情": "描写心情的成语",
    "时间": "与时间有关的成语",
    "数字": "含有数字的成语",
    "AABB": "AABB 结构的成语",
    "ABAC": "ABAC 结构的成语",
    "AABC": "AABC 结构的成语",
    "ABCC": "ABCC 结构的成语",
    "综合": "小学教辅常见成语",
}

FALLBACK_HINTS = {
    "万物复苏": "万物重新生长",
    "春回大地": "春天回来了，大地苏醒",
    "冰雪融化": "冰和雪化了",
    "泉水叮咚": "泉水发出叮咚声",
    "百花齐放": "很多花一起开",
    "百鸟争鸣": "很多鸟一起叫",
    "柳绿花红": "柳树绿、花儿红",
    "莺歌燕舞": "黄莺唱歌、燕子飞舞",
    "秋高气爽": "秋天天气清爽",
    "天高云淡": "天空高远，云很淡",
    "秋风习习": "秋风轻轻吹",
    "一叶知秋": "从一片落叶知道秋天到了",
    "金桂飘香": "桂花香气飘散",
    "层林尽染": "树林层层变色",
    "果实累累": "果实结得很多",
    "春华秋实": "春天开花秋天结果",
    "狼吞虎咽": "吃东西又猛又急",
    "惊弓之鸟": "受过惊吓后非常害怕",
    "胆小如鼠": "胆子很小",
    "龙飞凤舞": "字写得有气势",
    "漏网之鱼": "侥幸逃脱的人",
    "如虎添翼": "得到帮助后更强",
    "鸡鸣狗吠": "鸡叫狗叫形容喧闹",
    "害群之马": "危害集体的人",
    "如鱼得水": "做事非常顺手",
    "高山流水": "知音难遇或乐曲高妙",
    "天籁之音": "自然界最美的声音",
    "余音绕梁": "乐音很久还在回响",
    "黄钟大吕": "正宗高雅的音乐",
    "轻歌曼舞": "轻快地唱、柔美地舞",
    "行云流水": "文章或动作很流畅",
    "巧夺天工": "人工比自然还精巧",
    "惟妙惟肖": "描摹得十分逼真",
    "画龙点睛": "关键处一点就使整体生动",
    "笔走龙蛇": "书法笔势奔放",
    "妙笔生花": "文笔非常出色",
    "栩栩如生": "形象生动得像活的一样",
    "山清水秀": "风景优美",
    "自言自语": "自己跟自己说话",
    "鸟语花香": "鸟儿叫、花儿香",
    "和风细雨": "风很轻、雨很细",
    "云开雾散": "云雾散开，眼前明亮",
    "微风习习": "微风轻轻吹",
    "冰天雪地": "到处是冰和雪",
    "风雨交加": "又刮风又下雨",
    "鹅毛大雪": "雪片又大又密",
    "电闪雷鸣": "闪电打雷",
    "层林叠翠": "树林层层翠绿",
    "山穷水尽": "到了山和水的尽头，没有出路",
    "烟消云散": "像烟云一样消失了",
    "名山大川": "著名的高山和大河",
    "不言不语": "不说话",
    "只言片语": "很少的几句话",
    "三言两语": "几句话就说完",
    "千言万语": "有很多话要说",
    "豪言壮语": "气魄很大的话",
    "甜言蜜语": "说得很动听讨人喜欢",
    "少言寡语": "很少说话",
    "狐假虎威": "借别人的威势吓唬人",
    "坐井观天": "眼界很小",
    "无边无际": "大得看不到边",
    "神气活现": "自以为了不起的样子",
    "半信半疑": "有些信、有些不信",
    "东张西望": "这边看看那边看看",
    "大摇大摆": "走路很神气、满不在乎",
    "无影无踪": "完全看不见了",
    "名不虚传": "名声和实际相符",
    "四海为家": "到处都可以当作家",
    "安居乐业": "生活安定，工作愉快",
    "锦上添花": "好上加好",
    "雪中送炭": "在困难时给人帮助",
    "眉开眼笑": "高兴得眉眼都舒展开",
    "破涕为笑": "刚哭完又笑了",
    "捧腹大笑": "笑得直不起腰",
    "哈哈大笑": "大声地笑",
    "亡羊补牢": "出了问题赶紧补救还来得及",
    "揠苗助长": "急于求成反而把事情弄坏",
    "碧空如洗": "天空蓝得像洗过一样",
    "万里无云": "天空一片晴朗",
    "引人注目": "特别容易被人看见",
    "兴致勃勃": "兴趣很浓",
    "恋恋不舍": "舍不得离开",
    "四面八方": "周围各个方向",
    "和颜悦色": "脸色温和愉快",
    "筋疲力尽": "累得一点力气也没有",
    "生机勃勃": "充满活力",
    "摇头晃脑": "头摇来摇去，得意或入神",
    "披头散发": "头发散乱",
    "张牙舞爪": "凶狠或得意地挥舞",
    "提心吊胆": "十分担心害怕",
    "面红耳赤": "脸和耳朵都红了",
    "手忙脚乱": "做事慌张没有条理",
    "眼疾手快": "眼睛手都很快",
    "口干舌燥": "嘴里很干",
    "鸦雀无声": "非常安静",
    "糊里糊涂": "不清楚、弄不明白",
    "绚丽多彩": "色彩又多又好看",
    "一本正经": "样子很庄重认真",
    "大吃一惊": "非常吃惊",
    "成群结队": "很多人或动物聚在一起",
    "五光十色": "色彩繁多",
    "瑰丽无比": "美丽得没有谁能比",
    "恍然大悟": "一下子明白过来",
    "邯郸学步": "模仿别人反而把自己的本事忘了",
    "滥竽充数": "没有真本事却混在里面",
    "掩耳盗铃": "自己骗自己",
    "自相矛盾": "自己的说法或做法互相冲突",
    "刻舟求剑": "情况变了还用老办法",
    "画蛇添足": "做多余的事反而坏事",
    "杞人忧天": "为不必担心的事发愁",
    "井底之蛙": "见识很短浅",
    "杯弓蛇影": "疑神疑鬼，自己吓自己",
    "守株待兔": "不想努力，只等现成的",
    "争奇斗艳": "比谁更美丽出众",
    "窃窃私语": "小声地私下说话",
    "奔流不息": "一直不停地流",
    "无忧无虑": "没有烦恼",
    "灰心丧气": "失去信心，情绪低落",
    "没精打采": "没有精神",
    "名扬中外": "名声传到国内外",
    "形态各异": "样子各不相同",
    "腾云驾雾": "本领很大，像能驾着云雾飞",
    "上天入地": "本领极大，哪儿都能去",
    "神机妙算": "计谋非常高明",
    "各显神通": "各自拿出本事",
    "三头六臂": "本领特别大",
    "刀枪不入": "什么都伤害不了",
    "神通广大": "办法很多，本领很大",
    "未卜先知": "事情还没发生就知道",
    "人声鼎沸": "人声嘈杂得像开了锅",
    "风平浪静": "没有风浪，也指局势安定",
    "浩浩荡荡": "气势很大、规模很大",
    "山崩地裂": "山塌地裂，声势极大",
    "精疲力竭": "精神力气都用尽了",
    "随遇而安": "到哪儿都能安下心来",
    "左顾右盼": "这边看看那边看看",
    "局促不安": "拘束、心里不踏实",
    "一丝不苟": "一点儿也不马虎",
    "漫天卷地": "铺天盖地而来",
    "若隐若现": "一会儿看得见一会儿看不见",
    "囊萤夜读": "用萤火虫的光夜里读书",
    "悬梁刺股": "刻苦学习，不敢打瞌睡",
    "凿壁偷光": "想尽办法读书",
    "铁杵成针": "只要肯下功夫就能成功",
    "程门立雪": "恭敬地向老师求教",
    "手不释卷": "书一直拿在手里，非常爱读",
    "临危不惧": "遇到危险也不害怕",
    "彬彬有礼": "文雅有礼貌",
    "焦躁不安": "心里着急、烦躁",
    "心急如焚": "心里急得像火烧",
    "从容不迫": "不慌不忙",
    "惊慌失措": "吓得不知道该怎么办",
    "变化多端": "变化很多",
    "五彩斑斓": "颜色又多又好看",
    "天高地阔": "天地非常广阔",
    "依山傍水": "靠近山、靠近水",
    "鸡犬相闻": "能听见邻家鸡狗的叫声，形容住得近",
    "无能为力": "没有办法可想",
    "欣喜若狂": "高兴得快要发狂",
    "国泰民安": "国家太平，人民安乐",
    "政通人和": "政事顺利，百姓和睦",
    "人寿年丰": "人长寿，收成好",
    "夜不闭户": "夜里不用关门，社会安定",
    "路不拾遗": "丢在路上的东西也没人捡走",
    "多事之秋": "事故很多的时期",
    "兵荒马乱": "战争造成的混乱",
    "流离失所": "无家可归，四处流浪",
    "生灵涂炭": "百姓生活在极端困苦中",
    "家破人亡": "家庭毁了，人也没了",
    "哀鸿遍野": "到处是流离失所的灾民",
    "民不聊生": "人民没法生活下去",
    "内忧外患": "内部困难又加上外来威胁",
    "完璧归赵": "把东西完好无损地归还原主",
    "渑池会面": "蔺相如在渑池会上维护赵国尊严",
    "负荆请罪": "主动认错、请求责罚",
    "同心协力": "齐心合力",
    "足智多谋": "智谋很多",
    "诡计多端": "坏主意很多",
    "呕心沥血": "费尽心思",
    "处心积虑": "费尽心思谋划（多含贬义）",
    "美中不足": "大体很好，还有一点缺憾",
    "神气十足": "很得意、很有精神的样子",
    "理所当然": "按道理就该这样",
    "寸草不生": "什么植物都长不出来",
    "失魂落魄": "吓得或急得没了主意",
    "震耳欲聋": "声音大得耳朵都要聋了",
    "人山人海": "人非常多",
    "得意扬扬": "称心如意、神气十足",
    "迫不及待": "急得不能再等",
    "眉清目秀": "五官清秀好看",
    "亭亭玉立": "身材修长美丽",
    "明眸皓齿": "眼睛明亮、牙齿洁白",
    "文质彬彬": "举止文雅",
    "相貌堂堂": "仪表端正、很有气派",
    "威风凛凛": "气势使人敬畏",
    "膀大腰圆": "身材魁梧",
    "短小精悍": "个子小但精明强干",
    "容光焕发": "脸上很有光彩、很有精神",
    "鹤发童颜": "头发白了，脸色却像小孩一样红润",
    "慈眉善目": "样子慈善和气",
    "老态龙钟": "年老体衰、行动不灵便",
    "情不自禁": "自己控制不住感情",
    "胸有成竹": "心里早有了主意",
    "摩拳擦掌": "跃跃欲试、准备动手",
    "跃跃欲试": "很想马上试一试",
    "出谋划策": "出主意、想办法",
    "养尊处优": "生活在优裕的环境里",
    "踉踉跄跄": "走路不稳，跌跌撞撞",
    "哭笑不得": "不知该哭还是该笑",
    "喜不自胜": "高兴得自己都受不住",
    "天造地设": "像是天地特意安排的，非常合适",
    "抓耳挠腮": "着急或高兴得又抓耳朵又挠腮",
    "肃然起敬": "不由得产生敬意",
    "一针见血": "说话直截了当，一下子说到要害",
    "居高临下": "占据高处，向下俯视",
    "粉身碎骨": "身体粉碎，也指不惜牺牲",
    "斩钉截铁": "说话办事坚决果断",
    "全神贯注": "精神完全集中",
    "热血沸腾": "情绪非常激动",
    "横七竖八": "乱七八糟地摆着",
    "昂首挺胸": "抬起头、挺起胸，很有精神",
    "气壮山河": "气势像高山大河一样雄伟",
    "惊天动地": "声势或影响极大",
    "迎风招展": "在风里飘动",
    "排山倒海": "力量非常强大",
    "五颜六色": "颜色很多",
    "别出心裁": "想出和别人不一样的办法",
    "技高一筹": "本领比别人高一截",
    "虎视眈眈": "像老虎一样盯着，想扑上去",
    "忘乎所以": "得意得忘了自己是谁",
    "暴露无遗": "全部显露出来，什么也藏不住",
    "津津有味": "吃或听得非常有兴趣",
    "一望无际": "一眼望不到边",
    "无穷无尽": "没有尽头",
    "囫囵吞枣": "不加咀嚼地整吞，比喻不求甚解",
    "张冠李戴": "弄错了对象或事实",
    "饱经风霜": "经历过很多艰苦",
    "司空见惯": "看惯了，不觉得奇怪",
    "追根求源": "找出事物的根由",
    "见微知著": "从细小处看出大趋势",
    "锲而不舍": "一直坚持，不放弃",
    "五湖四海": "全国各地，四面八方",
    "精兵简政": "精简机构、减少人员",
    "死得其所": "死得有意义、有价值",
    "喜出望外": "没想到的好事让人高兴",
    "奄奄一息": "只剩下一口气，快不行了",
    "无独有偶": "不止一个，还有配对的",
    "万象更新": "一切都换成了新气象",
    "截然不同": "完全不一样",
    "万不得已": "实在没有别的办法",
    "不可思议": "无法想象，很难理解",
}


def theme_of(word: str) -> str:
    if AABB.match(word):
        return "AABB"
    if ABAC.match(word):
        return "ABAC"
    if AABC.match(word):
        return "AABC"
    if ABCC.match(word):
        return "ABCC"
    for theme, keys in THEME_RULES:
        if any(k in word for k in keys):
            return theme
    return "综合"


def level_of(word: str, theme: str, l1: set[str], rank: int) -> str:
    if word in l1:
        return "L1"
    if theme in {"春天", "秋天", "冬天", "夏天", "动物", "外貌", "写景", "AABB"} and rank < 400:
        return "L2"
    if theme in {"寓言", "艺术", "场面"} and rank < 500:
        return "L2"
    if theme in {"学习", "品质", "心情", "时间", "数字", "历史", "神态", "综合", "ABAC", "AABC", "ABCC"}:
        return "L3"
    return "L3"


def make_prompt(hint: str, word: str) -> str:
    hint = hint.strip()
    # avoid leaking full answer at start
    if hint.startswith(word):
        hint = simplify_explanation(hint, word)
    if word in hint:
        hint = hint.replace(word, "……")
    if not hint:
        hint = "小学教辅常见成语"
    suffix = "（四字）" if len(word) == 4 else "（成语）"
    if hint.endswith("（四字）") or hint.endswith("（成语）"):
        return hint
    return hint + suffix


def priority(word: str, l1: set[str], theme: str) -> tuple:
    # lower is better
    if word in l1:
        return (0, word)
    theme_rank = {
        "寓言": 1,
        "学习": 2,
        "品质": 3,
        "写景": 4,
        "场面": 5,
        "外貌": 6,
        "神态": 7,
        "心情": 8,
        "动物": 9,
        "艺术": 10,
        "历史": 11,
        "春天": 12,
        "秋天": 13,
        "冬天": 14,
        "夏天": 15,
        "时间": 16,
        "数字": 17,
        "AABB": 18,
        "ABAC": 19,
        "综合": 20,
    }.get(theme, 30)
    return (theme_rank, word)


def build() -> dict:
    xinhua = load_xinhua()
    textbook = load_textbook()
    l1 = set(textbook)
    existing_keys = load_existing_keys()
    reserved_keys = set(existing_keys.values())
    seeds = [w.strip() for w in SEED.read_text(encoding="utf-8").splitlines() if w.strip()]
    for w in existing_keys:
        if w not in seeds:
            seeds.append(w)
    for w in textbook:
        if w not in seeds:
            seeds.insert(0, w)

    seen: set[str] = set()
    ordered_words: list[str] = []
    for w in seeds:
        if not re.fullmatch(r"[\u4e00-\u9fff]{3,8}", w):
            continue
        if w in seen:
            continue
        seen.add(w)
        ordered_words.append(w)

    ranked = sorted(
        ordered_words,
        key=lambda w: priority(w, l1, theme_of(w)),
    )

    points = []
    used_keys: set[str] = set()
    for i, word in enumerate(ranked, 1):
        theme = theme_of(word)
        level = level_of(word, theme, l1, i)
        book = textbook.get(word)
        row = xinhua.get(word, {})
        hint = FALLBACK_HINTS.get(word) or simplify_explanation(row.get("explanation") or "", word)
        if not hint:
            hint = THEME_DEFAULT_HINT.get(theme, "小学教辅常见成语")
        if book:
            tags = book["tags"]
            source = book["source"]
            grade = book["grade"]
            group = book["group"]
            sub_group = book["sub_group"]
        elif level == "L2":
            tags = f"成语;{theme};课内拓展"
            source = "小学成语培优全书·教辅常见"
            grade = ""
            group = f"成语-{theme}"
            sub_group = level
        else:
            tags = f"成语;{theme};小升初高频"
            source = "小学成语培优全书·教辅常见"
            grade = ""
            group = f"成语-{theme}"
            sub_group = level
        key = assign_key(word, existing_keys, used_keys, reserved_keys)
        used_keys.add(key)
        points.append(
            {
                "key": key,
                "kind": "idiom",
                "level": level,
                "grade": grade,
                "prompt": make_prompt(hint, word),
                "answer": word,
                "tags": tags,
                "source": source,
                "group": group,
                "sub_group": sub_group,
            }
        )
    return {
        "title": "小学成语",
        "version": 3,
        "count": len(points),
        "points": points,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pack = build()
    points = pack["points"]
    assert points, "no idioms"
    assert len({p["answer"] for p in points}) == len(points)

    # soft validate lengths
    for p in points:
        n = len(re.sub(r"\s+", "", p["answer"]))
        if not 3 <= n <= 8:
            raise SystemExit(f"bad length {p['answer']}")

    json_path = OUT_DIR / JSON_NAME
    csv_path = OUT_DIR / CSV_NAME
    json_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fields = ["kind", "level", "grade", "prompt", "answer", "tags", "source", "key", "group", "sub_group"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for p in points:
            w.writerow({k: p.get(k, "") for k in fields})

    PRINTABLE_MD.write_text(printable_markdown(load_textbook_blocks()), encoding="utf-8")

    levels = Counter(p["level"] for p in points)
    grades = Counter(p["grade"] for p in points if p.get("grade"))
    themes = Counter((p["tags"].split(";")[1] if ";" in p["tags"] else "") for p in points)
    readme = f"""# 小学成语（{pack['count']} 条）

面向小学生、教辅与小升初常见考点的成语知识点包。候选清单里收集到的四字成语全部收录。

课内必背以 `textbook_by_grade.json` 为准（统编 1–6 年级，分日积月累 / 课文），带年级。打印原文见 `raw/小学成语.md`。

## 文件

- `{CSV_NAME}`：CSV 备份
- `{JSON_NAME}`：含稳定 `key` / `group`，官方材料同步用
- `textbook_by_grade.json`：统编课内成语分类（权威清单）

## 级别分布

| 级别 | 含义 | 数量 |
|---|---|---|
| L1 | 课内必背（按册、分日积月累/课文） | {levels.get('L1', 0)} |
| L2 | 课内拓展 / 作文常见 | {levels.get('L2', 0)} |
| L3 | 小升初高频 / 教辅常见 | {levels.get('L3', 0)} |

课内按年级：{'；'.join(f'{g} {n}' for g, n in sorted(grades.items(), key=lambda item: GRADE_ORDER.index(item[0])))}

## 导入

已作为官方材料「小学成语」，在「原始资料」同步后直接进知识库，不用审核。改本目录 JSON 后做增量同步即可。

## 说明

- 词条来自小学教辅高频分类与统编课内成语，释义提示面向默写。
- 同一成语若跨册出现，按首次出现的年级收录，出处里保留全部册次。
- 开源成语库仅用于补全短提示；当前共 {pack['count']} 条。
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")
    # also keep seed snapshot in repo for reproducibility
    (OUT_DIR / "seed_words.txt").write_text(
        "\n".join(p["answer"] for p in points) + "\n", encoding="utf-8"
    )
    print("count", len(points))
    print("levels", dict(levels))
    print("grades", dict(grades))
    print("themes", themes.most_common(15))
    print("sample")
    for p in points[:8]:
        print(p["level"], p.get("grade") or "-", p["answer"], p["source"], p["prompt"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
