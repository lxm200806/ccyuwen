#!/usr/bin/env python3
"""从教辅高频成语清单生成约 1200 条可导入知识点。"""
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
XINHUA = Path("/tmp/idiom.json")
TARGET = 1200

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


def textbook_l1() -> set[str]:
    out: set[str] = set()
    for path in (ROOT / "raw").glob("部编*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for point in data.get("points", []):
            if point.get("kind") == "idiom":
                ans = str(point.get("answer") or "").strip()
                if re.fullmatch(r"[\u4e00-\u9fff]{3,8}", ans):
                    out.add(ans)
    return out


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
    l1 = textbook_l1()
    seeds = [w.strip() for w in SEED.read_text(encoding="utf-8").splitlines() if w.strip()]
    # ensure all textbook idioms included
    for w in l1:
        if w not in seeds:
            seeds.insert(0, w)

    # dedupe preserve order
    seen: set[str] = set()
    ordered_words: list[str] = []
    for w in seeds:
        if not re.fullmatch(r"[\u4e00-\u9fff]{4}", w):
            continue
        if w in seen:
            continue
        seen.add(w)
        ordered_words.append(w)

    ranked = sorted(
        ordered_words,
        key=lambda w: priority(w, l1, theme_of(w)),
    )[:TARGET]

    points = []
    for i, word in enumerate(ranked, 1):
        theme = theme_of(word)
        level = level_of(word, theme, l1, i)
        row = xinhua.get(word, {})
        hint = FALLBACK_HINTS.get(word) or simplify_explanation(row.get("explanation") or "", word)
        if not hint:
            hint = THEME_DEFAULT_HINT.get(theme, "小学教辅常见成语")
        if level == "L1":
            tags = f"成语;{theme};课内必背"
            source = "部编教材日积月累/课内"
        elif level == "L2":
            tags = f"成语;{theme};课内拓展"
            source = "小学成语培优全书·教辅常见"
        else:
            tags = f"成语;{theme};小升初高频"
            source = "小学成语培优全书·教辅常见"
        points.append(
            {
                "key": f"idiom-{level.lower()}-{i:04d}",
                "kind": "idiom",
                "level": level,
                "grade": "",
                "prompt": make_prompt(hint, word),
                "answer": word,
                "tags": tags,
                "source": source,
                "group": f"成语-{theme}",
                "sub_group": level,
            }
        )
    return {
        "title": "小学成语培优全书（教辅常见约1200）",
        "version": 1,
        "count": len(points),
        "points": points,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pack = build()
    points = pack["points"]
    assert len(points) == TARGET, len(points)
    assert len({p["answer"] for p in points}) == TARGET

    # soft validate lengths
    for p in points:
        n = len(re.sub(r"\s+", "", p["answer"]))
        if not 3 <= n <= 8:
            raise SystemExit(f"bad length {p['answer']}")

    json_path = OUT_DIR / "小学成语1200.json"
    csv_path = OUT_DIR / "小学成语1200.csv"
    json_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fields = ["kind", "level", "grade", "prompt", "answer", "tags", "source", "key", "group", "sub_group"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for p in points:
            w.writerow({k: p.get(k, "") for k in fields})

    levels = Counter(p["level"] for p in points)
    themes = Counter(p["tags"].split(";")[1] for p in points)
    readme = f"""# 小学成语培优全书（{pack['count']} 条）

面向小学生、教辅与小升初常见考点的成语知识点包。

## 文件

- `小学成语1200.csv`：审核页 CSV 导入
- `小学成语1200.json`：含稳定 `key` / `group`

## 级别分布

| 级别 | 含义 | 数量 |
|---|---|---|
| L1 | 课内必背 | {levels.get('L1', 0)} |
| L2 | 课内拓展 / 作文常见 | {levels.get('L2', 0)} |
| L3 | 小升初高频 / 教辅常见 | {levels.get('L3', 0)} |

## 导入

管理端上传 CSV/JSON → 抽进草稿 → 校对发布。

## 说明

- 词条来自小学教辅高频分类与部编课内成语，释义提示面向默写。
- 开源成语库仅用于补全短提示；已去重为恰好 {TARGET} 条。
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")
    # also keep seed snapshot in repo for reproducibility
    (OUT_DIR / "seed_words.txt").write_text(
        "\n".join(p["answer"] for p in points) + "\n", encoding="utf-8"
    )
    print("count", len(points))
    print("levels", dict(levels))
    print("themes", themes.most_common(15))
    print("sample")
    for p in points[:5]:
        print(p["level"], p["answer"], p["prompt"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
