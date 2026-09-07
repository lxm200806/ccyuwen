"""核心逻辑自检，不连数据库。"""
import unittest

from app.auth import demo_hints_enabled
from app.study_modes import (
    apply_today_mode,
    default_study_mode,
    normalize_mode,
    resolve_default_mode,
    review_outcome,
    answer_lines,
)
from app.progress import (
    build_progress,
    kid_feedback,
    mastery_counts,
    parent_copy,
    progress_status,
    time_cap_state,
    week_brief,
)
from app.wizard import wizard_plan
from app.cards import (
    decode_filters,
    encode_filters,
    fill_group_fields,
    page_args,
    parse_import,
    parse_resource_filter,
    plan_course_days,
    plan_today_groups,
    point_energy,
    validate_card,
)
from app.grade import grade_answer, grade_card, grade_char_judge, grade_choice, normalize
from app.sm2 import add_days, is_mastered, schedule


def recite_points(points):
    return [
        point
        for point in points
        if (point.get("question_type") or "dictation") in {"recite", "dictation"}
    ]


def points_by_lemma(points):
    return {(point.get("lemma") or point.get("answer") or ""): point for point in recite_points(points)}


class GradeTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("床前明月 光，"), "床前明月光")
        self.assertEqual(normalize(None), "")

    def test_exact(self):
        result = grade_answer(
            "床前明月光，疑是地上霜。举头望明月，低头思故乡。",
            "床前明月光，疑是地上霜。举头望明月，低头思故乡。",
        )
        self.assertEqual(result["quality"], 5)
        self.assertTrue(result["correct"])

    def test_empty(self):
        self.assertEqual(grade_answer("", "己")["quality"], 1)

    def test_idiom_typo(self):
        self.assertEqual(grade_answer("守株侍兔", "守株待兔")["quality"], 1)

    def test_char_judge_and_choice(self):
        self.assertEqual(grade_char_judge("对", "对")["quality"], 5)
        self.assertEqual(grade_char_judge("错", "对")["quality"], 1)
        self.assertEqual(grade_char_judge("正确", "对")["quality"], 5)
        self.assertEqual(grade_choice("做事认真", "做事认真")["quality"], 5)
        self.assertEqual(grade_choice("1", "做事认真")["quality"], 1)
        judged = grade_card({"question_type": "char_judge", "answer": "错"}, "错")
        self.assertTrue(judged["correct"])
        choice = grade_card({"question_type": "meaning_choice", "answer": "形容认真"}, "形容认真")
        self.assertTrue(choice["correct"])
        revealed = grade_card({"question_type": "char_judge", "answer": "对"}, "", reveal=True)
        self.assertFalse(revealed["correct"])


class Sm2Tests(unittest.TestCase):
    def test_schedule(self):
        first = schedule(None, 5, "2026-09-02")
        self.assertEqual(first["interval"], 1)
        self.assertEqual(first["due"], "2026-09-03")
        second = schedule(first, 5, "2026-09-03")
        self.assertEqual(second["interval"], 6)
        fail = schedule(second, 1, "2026-09-09")
        self.assertEqual(fail["n"], 0)
        self.assertEqual(fail["lapses"], 1)

    def test_mastered(self):
        self.assertTrue(is_mastered({"interval": 21, "n": 4}))
        self.assertFalse(is_mastered({"interval": 6, "n": 2}))
        self.assertFalse(is_mastered(None))

    def test_add_days(self):
        self.assertEqual(add_days("2026-09-02", 6), "2026-09-08")


class CardTests(unittest.TestCase):
    def test_size_limits(self):
        self.assertIsNone(validate_card("zi", "写", "己"))
        self.assertIsNotNone(validate_card("zi", "写", "已经"))
        self.assertIsNotNone(validate_card("poem", "默写", "字" * 81))
        self.assertIsNone(validate_card("wenyan", "默写文言文", "宋人有耕者。田中有株。"))
        self.assertIsNotNone(validate_card("wenyan", "默写文言文", "字" * 161))
        self.assertIsNone(validate_card("idiom", "意思", "守株待兔"))
        self.assertIsNone(validate_card("saying", "俗语", "人心齐，泰山移。"))
        self.assertIsNotNone(validate_card("saying", "俗语", "字" * 41))
        self.assertIsNone(validate_card("sentence", "句子", "风，是大自然的音乐家。"))
        self.assertIsNone(validate_card("idiom", "写法", "对", "char_judge", "守株待兔"))
        self.assertIsNone(validate_card("idiom", "意思", "做事很认真", "meaning_choice", "守株待兔"))

    def test_csv_import(self):
        parsed = parse_import(
            "kind,level,grade,prompt,answer,tags,source\npoem,L3,三年级上,欲穷千里目，______。,更上一层楼,名句,真题"
        )
        self.assertEqual(len(parsed["ok"]), 1)
        self.assertEqual(parsed["ok"][0]["answer"], "更上一层楼")
        self.assertEqual(parsed["ok"][0]["grade"], "三年级上")

    def test_skip_empty(self):
        self.assertEqual(parse_import("[{}]")["skip"], 1)
        self.assertEqual(parse_import("")["ok"], [])

    def test_filters_and_page(self):
        self.assertEqual(encode_filters(["poem", "bad", "zi"], ("poem", "idiom", "zi")), "poem,zi")
        self.assertEqual(decode_filters("poem,L9,zi", ("poem", "idiom", "zi")), ["poem", "zi"])
        self.assertEqual(page_args(0, -3), (1, 0))
        self.assertEqual(page_args(9999, 10), (500, 10))
        self.assertIsNone(parse_resource_filter(None))
        self.assertIsNone(parse_resource_filter(""))
        self.assertIsNone(parse_resource_filter("all"))
        self.assertIsNone(parse_resource_filter("undefined"))
        self.assertEqual(parse_resource_filter("0"), 0)
        self.assertEqual(parse_resource_filter("unlinked"), 0)
        self.assertEqual(parse_resource_filter(None, unlinked=True), 0)
        self.assertEqual(parse_resource_filter("12"), 12)
        self.assertIsNone(parse_resource_filter("abc"))


class Grade3aTests(unittest.TestCase):
    def test_all_points_valid(self):
        from app.grade3a_points import GRADE3A_POINTS

        self.assertEqual(len(GRADE3A_POINTS), 40)
        keys = [point["key"] for point in GRADE3A_POINTS]
        self.assertEqual(len(keys), len(set(keys)))
        for point in GRADE3A_POINTS:
            error = validate_card(point["kind"], point["prompt"], point["answer"])
            self.assertIsNone(error, point["prompt"] + " " + str(error))
            self.assertEqual(point["grade"], "三年级上")
            self.assertTrue(point["key"])
            self.assertTrue(point["source"])
            self.assertTrue(point["level"])
        self.assertEqual(next(item["kind"] for item in GRADE3A_POINTS if item["key"] == "g3s-poem-simaguang"), "wenyan")

    def test_original_and_pack(self):
        from app.materials import (
            GRADE_PACKS,
            IDIOM_PACK,
            PACKS,
            bundled_md,
            dump_pack,
            find_pack,
            is_grade_pack,
            load_pack,
            read_original,
        )

        spec = find_pack("grade3-shang")
        original = read_original(spec) or bundled_md(spec).read_text(encoding="utf-8")
        self.assertIn("日积月累", original)
        self.assertGreater(len(original), 200)
        pack = load_pack(spec)
        self.assertIn("日积月累", pack["original"])
        self.assertEqual(len(spec["points"]), 40)
        self.assertGreaterEqual(len(pack["points"]), 40)
        parsed = parse_import(dump_pack(pack))
        self.assertEqual(len(parsed["ok"]), len(pack["points"]))
        self.assertEqual(parsed["ok"][0]["key"], pack["points"][0]["key"])

        keys = []
        self.assertEqual(len(GRADE_PACKS), 12)
        self.assertEqual(len(PACKS), 13)
        self.assertEqual(IDIOM_PACK["title"], "小学成语")
        self.assertTrue(is_grade_pack("grade3-shang"))
        self.assertFalse(is_grade_pack("elementary-idioms"))
        idioms = load_pack(find_pack("elementary-idioms"))
        recite = recite_points(idioms["points"])
        self.assertGreaterEqual(len(recite), 1900, "elementary-idioms")
        self.assertGreaterEqual(len({point.get("entry_key") for point in idioms["points"]}), 1900)
        self.assertTrue(any(point["kind"] == "idiom" for point in idioms["points"]))
        by_lemma = points_by_lemma(idioms["points"])
        self.assertEqual(by_lemma["山清水秀"]["grade"], "一年级上")
        self.assertIn("课文", by_lemma["山清水秀"]["source"])
        self.assertEqual(by_lemma["春回大地"]["grade"], "一年级下")
        self.assertIn("日积月累", by_lemma["春回大地"]["source"])
        self.assertEqual(by_lemma["狐假虎威"]["grade"], "二年级上")
        self.assertEqual(by_lemma["自言自语"]["grade"], "一年级上")
        self.assertIn("二年级下册", by_lemma["自言自语"]["source"])
        sample = [point for point in idioms["points"] if (point.get("lemma") or "") == "山清水秀"]
        self.assertEqual({point.get("question_type") for point in sample}, {"recite", "char_judge", "meaning_choice"})
        self.assertGreaterEqual(sum(1 for point in recite if point.get("grade")), 240)
        self.assertIn("日积月累", idioms["original"])
        self.assertIn("课文成语", idioms["original"])
        for spec in GRADE_PACKS:
            loaded = load_pack(spec)
            self.assertIn("日积月累", loaded["original"], spec["slug"])
            self.assertGreater(len(loaded["points"]), 15, spec["slug"])
            keys.extend(point["key"] for point in loaded["points"])
            for point in loaded["points"]:
                error = validate_card(
                    point["kind"],
                    point["prompt"],
                    point["answer"],
                    point.get("question_type"),
                    point.get("lemma"),
                )
                self.assertIsNone(error, point["key"] + " " + str(error))
        keys.extend(point["key"] for point in idioms["points"])
        self.assertEqual(len(keys), len(set(keys)))

    def test_textbook_idioms_are_graded(self):
        import json
        from pathlib import Path

        from app.materials import find_pack, load_pack, raw_root

        data = json.loads((raw_root() / "idioms" / "textbook_by_grade.json").read_text(encoding="utf-8"))
        expected = []
        for block in data.get("blocks") or []:
            expected.extend(block.get("words") or [])
        self.assertGreaterEqual(len(set(expected)), 240)

        idioms = load_pack(find_pack("elementary-idioms"))
        by_lemma = points_by_lemma(idioms["points"])
        missing = [word for word in expected if word not in by_lemma]
        self.assertEqual(missing, [], "missing textbook idioms")
        self.assertEqual(by_lemma["不可思议"]["grade"], "六年级下")
        self.assertEqual(by_lemma["安居乐业"]["grade"], "二年级上")
        printable = Path(raw_root() / "小学成语.md").read_text(encoding="utf-8")
        self.assertIn("山清水秀、自言自语", printable)
        self.assertIn("无成语", printable)

    def test_original_lists_are_in_points(self):
        import re

        from app.grade import normalize
        from app.materials import GRADE_PACKS, read_original

        word_re = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
        missing = []
        for spec in GRADE_PACKS:
            original = read_original(spec)
            answers = normalize("".join(point["answer"] for point in spec["points"]))
            searchable = normalize("".join(point["answer"] + point["prompt"] for point in spec["points"]))
            section = original.split("## 二、", 1)
            daily = section[1].split("## 三、", 1)[0] if len(section) > 1 else ""
            for raw_line in daily.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or line.startswith("**"):
                    continue
                if "：" in line:
                    left, right = line.split("：", 1)
                    right = right.strip()
                    if len(left) <= 8 and right and normalize(right) and normalize(right) not in answers:
                        missing.append(spec["slug"] + " " + right[:30])
                    if len(left) <= 8:
                        line = right
                line = line.split("——")[0].strip()
                for chunk in re.split(r"[\s　]+", line):
                    chunk = chunk.strip("。；、：")
                    if word_re.match(chunk) and normalize(chunk) not in searchable:
                        missing.append(spec["slug"] + " " + chunk)
                if ("，" in line or "。" in line) and normalize(line) and normalize(line) not in answers:
                    missing.append(spec["slug"] + " " + line[:30])

            numbered = original.split("## 三、", 1)
            if len(numbered) > 1:
                for raw_line in numbered[1].splitlines():
                    match = re.match(r"^\d+\.\s*(.+?)(?:——|$)", raw_line.strip())
                    if not match:
                        continue
                    sentence = match.group(1).strip()
                    if sentence and normalize(sentence) not in answers:
                        missing.append(spec["slug"] + " sentence " + sentence[:20])
        self.assertEqual(missing, [], "\n".join(missing))

    def test_upsert_by_key_updates_same_row(self):
        from app.materials import upsert_published

        class FakeCur:
            def __init__(self):
                self.rows = {}
                self.next_id = 1
                self.result = None

            def execute(self, sql, args=None):
                text = " ".join(sql.split())
                args = args or ()
                if "knowledge_entry" in text:
                    self.result = None
                    return
                if "WHERE point_key" in text and text.strip().startswith("SELECT"):
                    self.result = next((row for row in self.rows.values() if row["point_key"] == args[0]), None)
                elif "WHERE prompt" in text:
                    qtype = args[2] if len(args) > 2 else "dictation"
                    self.result = next(
                        (
                            row
                            for row in self.rows.values()
                            if row["prompt"] == args[0]
                            and row["answer"] == args[1]
                            and (row.get("question_type") or "dictation") == qtype
                        ),
                        None,
                    )
                elif text.strip().startswith("UPDATE"):
                    row = self.rows[args[-1]]
                    keys = [
                        "kind", "level", "grade", "prompt", "answer", "tags", "source",
                        "source_resource_id", "point_key", "group_key", "sub_group_key",
                        "entry_key", "lemma", "question_type", "audience", "options",
                    ]
                    for index, key in enumerate(keys):
                        if index < len(args) - 1:
                            row[key] = args[index]
                    self.result = {"id": row["id"]}
                elif text.strip().startswith("INSERT"):
                    point_id = self.next_id
                    self.next_id += 1
                    keys = [
                        "kind", "level", "grade", "prompt", "answer", "tags", "source",
                        "source_resource_id", "point_key", "group_key", "sub_group_key",
                        "entry_key", "lemma", "question_type", "audience", "options",
                    ]
                    row = {"id": point_id}
                    for index, key in enumerate(keys):
                        if index < len(args):
                            row[key] = args[index]
                    self.rows[point_id] = row
                    self.result = {"id": point_id}

            def fetchone(self):
                return self.result

        cur = FakeCur()
        first = {
            "key": "g3s-poem-shanxing",
            "kind": "poem",
            "level": "L1",
            "grade": "三年级上",
            "prompt": "默写杜牧《山行》",
            "answer": "远上寒山石径斜",
            "tags": "古诗",
            "source": "三年级上",
        }
        point_id, status = upsert_published(cur, first, 1)
        self.assertEqual(status, "inserted")
        self.assertTrue(cur.rows[point_id]["group_key"])
        first["answer"] = "远上寒山石径斜，白云生处有人家。"
        same_id, status = upsert_published(cur, first, 1)
        self.assertEqual(status, "updated")
        self.assertEqual(point_id, same_id)
        self.assertEqual(cur.rows[point_id]["answer"], first["answer"])
        self.assertEqual(len(cur.rows), 1)
        same_id, status = upsert_published(cur, first, 1)
        self.assertEqual(status, "unchanged")

    def test_pack_version_bumps_when_points_change(self):
        from app.materials import dump_pack, load_pack, next_version, pack_fingerprint, parse_version

        pack = load_pack()
        self.assertGreaterEqual(parse_version(pack["version"]), 1)
        self.assertTrue(pack["contentHash"])
        parsed = parse_import(dump_pack(pack))
        self.assertEqual(len(parsed["ok"]), len(pack["points"]))
        same_hash = pack_fingerprint(pack)
        self.assertEqual(pack["contentHash"], same_hash)
        self.assertEqual(next_version(1, same_hash, same_hash), 1)
        self.assertEqual(next_version(1, same_hash, "changed"), 2)
        padded = dict(pack)
        padded["original"] = (pack.get("original") or "") + "\n\n"
        self.assertEqual(pack_fingerprint(padded), same_hash)
        stale = dict(pack)
        stale["points"] = [dict(item) for item in (pack.get("points") or [])]
        if stale["points"]:
            stale["points"][0] = dict(stale["points"][0], answer=str(stale["points"][0].get("answer") or "") + "改")
            self.assertNotEqual(pack_fingerprint(stale), same_hash)
            self.assertEqual(next_version(pack["version"], same_hash, pack_fingerprint(stale)), pack["version"] + 1)
        import json

        from app.materials import PACKS, raw_root

        spec = PACKS[0]
        json_path = raw_root() / spec["json_name"]
        if json_path.is_file():
            stored = json.loads(json_path.read_text(encoding="utf-8"))
            loaded = load_pack(spec)
            stored_ver = stored.get("version") or loaded["version"]
            self.assertIn(loaded["version"], {stored_ver, stored_ver + 1})


class GroupTests(unittest.TestCase):
    def test_same_module_shares_group(self):
        from app.materials import find_pack, load_pack

        pack = load_pack(find_pack("grade6-shang"))
        culture = [
            point
            for point in pack["points"]
            if point["source"].endswith("语文园地六") and "传统文化" in point["tags"]
        ]
        art = [
            point
            for point in pack["points"]
            if point["source"].endswith("语文园地七") and point["kind"] == "idiom"
        ]
        self.assertEqual(len(recite_points(culture)), 4)
        self.assertEqual(len(recite_points(art)), 12)
        self.assertGreaterEqual(len({point["group_key"] for point in culture}), 4)
        self.assertGreaterEqual(len({point["group_key"] for point in art}), 12)
        poem = next(point for point in pack["points"] if point["kind"] == "poem")
        self.assertEqual(poem["group_key"], poem["key"])
        self.assertEqual(poem["entry_key"], poem["key"])

    def test_shared_source_splits_by_theme(self):
        from app.materials import find_pack, load_pack

        pack = load_pack(find_pack("grade3-xia"))
        yuyan = [point for point in pack["points"] if point["tags"] == "成语;寓言"]
        bazi = [point for point in pack["points"] if point["tags"] == "成语;八字"]
        self.assertGreaterEqual(len(recite_points(yuyan)), 2)
        self.assertGreaterEqual(len(recite_points(bazi)), 2)
        self.assertGreaterEqual(len({point["group_key"] for point in yuyan}), 2)
        self.assertGreaterEqual(len({point["group_key"] for point in bazi}), 2)
        self.assertNotEqual(yuyan[0]["group_key"], bazi[0]["group_key"])

    def test_explicit_group_and_citation_source(self):
        left = fill_group_fields(
            {
                "key": "a",
                "kind": "saying",
                "grade": "一年级下",
                "prompt": "默写《论语》",
                "answer": "敏而好学，不耻下问。",
                "tags": "名句;论语;日积月累",
                "source": "部编一年级下册·语文园地七·《论语》",
            }
        )
        right = fill_group_fields(
            {
                "key": "b",
                "kind": "saying",
                "grade": "一年级下",
                "prompt": "默写董遇",
                "answer": "读书百遍，而义自见。",
                "tags": "名句;论语;日积月累",
                "source": "部编一年级下册·语文园地七",
            }
        )
        self.assertNotEqual(left["group_key"], right["group_key"])
        self.assertEqual(left["entry_key"], left["group_key"])
        custom = fill_group_fields(
            {
                "key": "c",
                "kind": "idiom",
                "grade": "六年级上",
                "prompt": "艺术成语",
                "answer": "高山流水",
                "tags": "成语;艺术",
                "source": "部编六年级上册·语文园地七",
                "group": "g1-custom",
                "sub_group": "g2-a",
            }
        )
        self.assertEqual(custom["group_key"], custom["entry_key"])
        self.assertEqual(custom["entry_key"], "idiom:高山流水")
        self.assertEqual(custom["sub_group_key"], "g2-a")


class EntryCardTests(unittest.TestCase):
    def test_idiom_entry_emits_three_cards(self):
        from app.entries import encode_options, fill_entry_fields, make_char_judge_card, make_meaning_card, meaning_hint, parse_options

        base = fill_entry_fields(
            {
                "key": "idiom-tb-0001",
                "kind": "idiom",
                "level": "L1",
                "grade": "一年级上",
                "prompt": "形容做事认真（四字）",
                "answer": "一丝不苟",
                "tags": "成语;品质",
                "source": "测试",
                "lemma": "一丝不苟",
                "question_type": "recite",
                "audience": "all",
            }
        )
        pool = [meaning_hint(base), "景色很美丽", "形容心情不好", "做事很认真"]
        judge = make_char_judge_card(base)
        meaning = make_meaning_card(base, pool)
        self.assertEqual(base["entry_key"], "idiom:一丝不苟")
        self.assertEqual(base["group_key"], judge["group_key"])
        self.assertEqual(meaning["entry_key"], base["entry_key"])
        self.assertEqual(len({base["key"], judge["key"], meaning["key"]}), 3)
        self.assertEqual(judge["audience"], "lower")
        self.assertEqual(meaning["audience"], "upper")
        self.assertIn(judge["answer"], {"对", "错"})
        options = parse_options(meaning.get("options") or encode_options(meaning.get("options")))
        self.assertIn("choices", options)
        self.assertEqual(len(options["choices"]), 4)

    def test_expand_adds_judge_for_short_zi_not_idiom(self):
        from app.entries import maybe_expand_pack_cards

        expanded = maybe_expand_pack_cards(
            [
                {"key": "z1", "kind": "zi", "level": "L1", "prompt": "写", "answer": "己"},
                {"key": "i1", "kind": "idiom", "level": "L1", "prompt": "春天（四字）", "answer": "春回大地"},
                {"key": "p1", "kind": "poem", "level": "L1", "prompt": "静夜思", "answer": "床前明月光"},
            ]
        )
        types = {(item["key"], item.get("question_type")) for item in expanded}
        self.assertIn(("z1", "dictation"), types)
        self.assertIn(("z1:char_judge", "char_judge"), types)
        self.assertIn(("i1", "recite"), types)
        self.assertFalse(any(item["key"].startswith("i1:") for item in expanded))
        self.assertEqual(next(item for item in expanded if item["key"] == "p1")["question_type"], "recite")

    def test_audiences_for_grades(self):
        from app.entries import audiences_for_grades

        self.assertEqual(audiences_for_grades(["一年级上"]), {"all", "lower"})
        self.assertEqual(audiences_for_grades(["五年级下"]), {"all", "upper"})
        self.assertEqual(audiences_for_grades(["三年级上"]), {"all", "lower", "upper"})
        self.assertIsNone(audiences_for_grades([]))

    def test_upsert_allows_second_card_same_lemma(self):
        from app.entries import fill_entry_fields, make_char_judge_card
        from app.materials import upsert_published

        class FakeCur:
            def __init__(self):
                self.rows = {}
                self.next_id = 1
                self.result = None

            def execute(self, sql, args=None):
                text = " ".join(sql.split())
                args = args or ()
                if "knowledge_entry" in text:
                    self.result = None
                    return
                if "WHERE point_key" in text and text.strip().startswith("SELECT"):
                    self.result = next((row for row in self.rows.values() if row.get("point_key") == args[0]), None)
                elif "WHERE prompt" in text:
                    qtype = args[2] if len(args) > 2 else "dictation"
                    self.result = next(
                        (
                            row
                            for row in self.rows.values()
                            if row["prompt"] == args[0]
                            and row["answer"] == args[1]
                            and (row.get("question_type") or "dictation") == qtype
                        ),
                        None,
                    )
                elif text.strip().startswith("INSERT"):
                    point_id = self.next_id
                    self.next_id += 1
                    keys = [
                        "kind", "level", "grade", "prompt", "answer", "tags", "source",
                        "source_resource_id", "point_key", "group_key", "sub_group_key",
                        "entry_key", "lemma", "question_type", "audience", "options",
                    ]
                    row = {"id": point_id}
                    for index, key in enumerate(keys):
                        if index < len(args):
                            row[key] = args[index]
                    self.rows[point_id] = row
                    self.result = {"id": point_id}

            def fetchone(self):
                return self.result

        cur = FakeCur()
        base = fill_entry_fields(
            {
                "key": "idiom-same",
                "kind": "idiom",
                "level": "L1",
                "grade": "一年级上",
                "prompt": "形容认真（四字）",
                "answer": "一丝不苟",
                "tags": "成语",
                "source": "测试",
                "question_type": "recite",
            }
        )
        first_id, status = upsert_published(cur, base, 1)
        self.assertEqual(status, "inserted")
        judge = make_char_judge_card(base)
        second_id, status = upsert_published(cur, judge, 1)
        self.assertEqual(status, "inserted")
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(len(cur.rows), 2)
        self.assertEqual(cur.rows[first_id]["entry_key"], cur.rows[second_id]["entry_key"])

    def test_upsert_entry_merges_grades_and_levels(self):
        from app.entries import fill_entry_fields
        from app.materials import upsert_entry

        class FakeCur:
            def __init__(self):
                self.entries = {}
                self.grades = set()
                self.levels = set()
                self.result = None

            def execute(self, sql, args=None):
                text = " ".join(sql.split())
                args = args or ()
                if text.strip().startswith("SELECT") and "FROM knowledge_entry" in text:
                    self.result = self.entries.get(args[0])
                    return
                if "INSERT INTO knowledge_entry " in text:
                    row = {
                        "entry_key": args[0],
                        "kind": args[1],
                        "lemma": args[2],
                        "grade": args[3],
                        "grades": args[4],
                        "levels": args[5],
                        "tags": args[6],
                        "source": args[7],
                    }
                    self.entries[args[0]] = row
                    self.result = None
                    return
                if "INSERT INTO knowledge_entry_grade" in text:
                    self.grades.add((args[0], args[1]))
                    self.result = None
                    return
                if "INSERT INTO knowledge_entry_level" in text:
                    self.levels.add((args[0], args[1]))
                    self.result = None

            def fetchone(self):
                return self.result

        cur = FakeCur()
        first = fill_entry_fields(
            {
                "kind": "idiom",
                "level": "L1",
                "grade": "一年级上",
                "prompt": "一年级",
                "answer": "春回大地",
                "lemma": "春回大地",
                "tags": "成语",
                "source": "一年级上",
                "question_type": "recite",
            }
        )
        second = fill_entry_fields(
            {
                "kind": "idiom",
                "level": "L3",
                "grade": "二年级上",
                "prompt": "二年级",
                "answer": "春回大地",
                "lemma": "春回大地",
                "tags": "成语",
                "source": "二年级上",
                "question_type": "recite",
            }
        )
        upsert_entry(cur, first)
        upsert_entry(cur, second)
        row = cur.entries[first["entry_key"]]
        self.assertEqual(row["lemma"], "春回大地")
        self.assertIn("一年级上", row["grades"])
        self.assertIn("二年级上", row["grades"])
        self.assertIn("L1", row["levels"])
        self.assertIn("L3", row["levels"])
        self.assertEqual(row["grade"], "一年级上")
        self.assertIn((first["entry_key"], "一年级上"), cur.grades)
        self.assertIn((first["entry_key"], "二年级上"), cur.grades)

    def test_pick_course_cards_keeps_one_per_entry_type(self):
        from app.entries import pick_course_cards

        rows = [
            {"id": 1, "entry_key": "idiom:春回大地", "question_type": "recite", "grade": "一年级下", "level": "L1", "kind": "idiom"},
            {"id": 2, "entry_key": "idiom:春回大地", "question_type": "recite", "grade": "二年级上", "level": "L3", "kind": "idiom"},
            {"id": 3, "entry_key": "idiom:春回大地", "question_type": "char_judge", "grade": "一年级下", "level": "L1", "kind": "idiom"},
            {"id": 4, "entry_key": "idiom:狐假虎威", "question_type": "recite", "grade": "二年级上", "level": "L1", "kind": "idiom"},
        ]
        picked = pick_course_cards(rows, ["二年级上"])
        by_key = {(row["entry_key"], row["question_type"]): row["id"] for row in picked}
        self.assertEqual(by_key[("idiom:春回大地", "recite")], 2)
        self.assertEqual(by_key[("idiom:春回大地", "char_judge")], 3)
        self.assertEqual(by_key[("idiom:狐假虎威", "recite")], 4)
        self.assertEqual(len(picked), 3)

    def test_plan_today_keeps_whole_group(self):
        def word(point_id, group, last=None, due=None):
            return {
                "id": point_id,
                "group_key": group,
                "last": last,
                "due": due,
                "kind": "idiom",
                "tags": "词语;秋天",
                "answer": "秋高气爽",
                "prompt": "秋天",
                "source": "园地一",
            }

        rows = [
            word(1, "g1-a"),
            word(2, "g1-a"),
            word(3, "g1-a"),
            word(4, "g1-b"),
            word(5, "g1-c", last="2026-08-01", due="2026-09-01"),
            word(6, "g1-c", last="2026-08-01", due="2026-09-10"),
        ]
        planned = plan_today_groups(rows, set(), "2026-09-02", new_energy=30, review_energy=30)
        self.assertEqual(planned["due"], 1)
        self.assertEqual(planned["fresh"], 2)
        picked_ids = [row["id"] for group in planned["groups"] for row in group["rows"]]
        self.assertEqual(picked_ids, [5, 1, 2, 3, 4])
        self.assertNotIn(6, picked_ids)
        self.assertEqual(planned["groups"][0]["role"], "review")
        self.assertEqual(planned["groups"][1]["role"], "new")


class EnergyTests(unittest.TestCase):
    def test_point_energy_by_kind(self):
        self.assertEqual(point_energy({"kind": "zi", "answer": "己"}), 1)
        self.assertEqual(point_energy({"kind": "idiom", "answer": "春风", "tags": "词语"}), 2)
        self.assertEqual(point_energy({"kind": "idiom", "answer": "高山流水", "tags": "成语;艺术"}), 4)
        self.assertEqual(point_energy({"kind": "idiom", "answer": "高山流水", "tags": "成语;艺术", "question_type": "recite"}), 2)
        self.assertEqual(point_energy({"kind": "idiom", "question_type": "char_judge", "answer": "对"}), 2)
        self.assertEqual(point_energy({"kind": "idiom", "question_type": "meaning_choice", "answer": "形容很好"}), 4)
        self.assertEqual(point_energy({"kind": "poem", "answer": "床前明月光，疑是地上霜。举头望明月，低头思故乡。"}), 16)
        self.assertEqual(point_energy({"kind": "wenyan", "answer": "宋人有耕者。" * 20}), 64)
        self.assertEqual(point_energy({"kind": "idiom", "answer": "高山流水", "tags": "成语", "energy": 8}), 8)

    def test_pack_by_daily_energy(self):
        light = {
            "kind": "idiom",
            "tags": "成语;艺术",
            "answer": "高山流水",
            "prompt": "艺术",
            "source": "园地七",
            "grade": "六年级上",
        }
        rows = [dict(light, id=index, group_key="g-" + str(index), energy=15, prompt="艺术" + str(index)) for index in range(1, 5)]
        planned = plan_course_days(rows, 30)
        self.assertGreaterEqual(planned["newDayCount"], 2)
        self.assertEqual(planned["days"][0]["newEnergy"], 30)
        self.assertEqual(planned["days"][0]["reviewEnergy"], 0)
        self.assertEqual(planned["days"][0]["cardCount"], 2)
        self.assertEqual(planned["days"][0]["pointCount"], 2)
        self.assertTrue(any(card["role"] == "review" for day in planned["days"] for card in day["cards"]))

        heavy = [dict(light, id=1, energy=50, kind="wenyan", answer="文" * 90, group_key="g-w")]
        heavy_plan = plan_course_days(heavy, 30, 30)
        self.assertEqual(heavy_plan["days"][0]["cards"][0]["parts"], 2)
        self.assertEqual(heavy_plan["days"][0]["cards"][0]["role"], "new")
        self.assertTrue(any(card["role"] == "review" for day in heavy_plan["days"] for card in day["cards"]))

        mid = [dict(light, id=1, energy=35, group_key="solo-1")]
        mid_plan = plan_course_days(mid, 30)
        self.assertEqual(mid_plan["days"][0]["newEnergy"], 35)
        self.assertEqual(mid_plan["newDayCount"], 1)


class StudyModeTests(unittest.TestCase):
    def test_normalize_and_default(self):
        self.assertEqual(normalize_mode("TEST"), "test")
        self.assertEqual(normalize_mode("背诵"), "recite")
        self.assertEqual(normalize_mode("nope"), "learn")
        self.assertEqual(
            default_study_mode({"groups": [{"role": "review"}], "reviewEnergy": 8, "newEnergy": 16}),
            "test",
        )
        self.assertEqual(
            default_study_mode({"groups": [{"role": "new"}], "reviewEnergy": 0, "newEnergy": 16}),
            "learn",
        )
        mixed = {"groups": [{"role": "new"}, {"role": "review"}], "reviewEnergy": 8, "newEnergy": 16}
        self.assertEqual(default_study_mode(mixed), "learn")
        self.assertEqual(resolve_default_mode(mixed, False), "learn")
        self.assertEqual(resolve_default_mode(mixed, True), "test")
        self.assertEqual(
            resolve_default_mode({"groups": [{"role": "new"}], "reviewEnergy": 0, "newEnergy": 16}, True),
            "learn",
        )

    def test_test_mode_prefers_review_groups(self):
        groups = [
            {"role": "review", "energy": 8, "rows": [1]},
            {"role": "new", "energy": 16, "rows": [2, 3]},
        ]
        planned = apply_today_mode({"groups": groups, "due": 1, "fresh": 1}, "test")
        self.assertEqual(len(planned["groups"]), 1)
        self.assertEqual(planned["groups"][0]["role"], "review")
        self.assertEqual(planned["reviewEnergy"], 8)
        self.assertEqual(planned["newEnergy"], 0)
        self.assertTrue(planned["energyCharged"])

        fallback = apply_today_mode({"groups": [{"role": "new", "energy": 4, "rows": [1]}]}, "test")
        self.assertEqual(len(fallback["groups"]), 1)
        self.assertEqual(fallback["newEnergy"], 4)

    def test_learn_keeps_mixed_queue(self):
        groups = [
            {"role": "review", "energy": 8, "rows": [1]},
            {"role": "new", "energy": 16, "rows": [2, 3]},
        ]
        planned = apply_today_mode({"groups": groups}, "learn")
        self.assertEqual(len(planned["groups"]), 2)
        self.assertEqual(planned["newEnergy"], 16)
        self.assertEqual(planned["reviewEnergy"], 8)

    def test_recite_zero_energy(self):
        groups = [{"role": "new", "energy": 16, "rows": [1, 2]}]
        planned = apply_today_mode({"groups": groups}, "recite")
        self.assertEqual(planned["newEnergy"], 0)
        self.assertEqual(planned["reviewEnergy"], 0)
        self.assertFalse(planned["energyCharged"])
        self.assertEqual(planned["cards"], 2)

    def test_learn_reveal_is_soft_quality_3(self):
        outcome = review_outcome("learn", {"quality": 1, "correct": False}, revealed=True)
        self.assertEqual(outcome["quality"], 3)
        self.assertTrue(outcome["update_sm2"])
        self.assertFalse(outcome["correct"])
        first = schedule(None, 5, "2026-09-02")
        peeked = schedule(first, outcome["quality"], "2026-09-03")
        failed = schedule(first, 1, "2026-09-03")
        self.assertEqual(peeked["n"], 2)
        self.assertEqual(peeked["lapses"], 0)
        self.assertEqual(failed["n"], 0)
        self.assertEqual(failed["lapses"], 1)
        self.assertLess(peeked["ef"], first["ef"])

    def test_test_reveal_rejected_and_strict_pass(self):
        blocked = review_outcome("test", {"quality": 1, "correct": False}, revealed=True)
        self.assertFalse(blocked["ok"])
        passed = review_outcome("test", {"quality": 5, "correct": True}, revealed=False)
        self.assertEqual(passed["quality"], 5)
        self.assertTrue(passed["update_sm2"])

    def test_recite_skips_sm2(self):
        outcome = review_outcome("recite", {"quality": 5, "correct": True}, revealed=False)
        self.assertTrue(outcome["ok"])
        self.assertFalse(outcome["update_sm2"])

    def test_answer_lines(self):
        self.assertEqual(answer_lines("春眠不觉晓。处处闻啼鸟。"), ["春眠不觉晓。", "处处闻啼鸟。"])
        self.assertEqual(answer_lines("春风"), ["春风"])


class ProgressTests(unittest.TestCase):
    def test_status_and_student_copy(self):
        remaining = build_progress(
            {"cards": 8, "tasks": 1, "newEnergy": 16, "reviewEnergy": 0, "newBudget": 30, "reviewBudget": 30},
            [],
            item_count=10,
        )
        self.assertEqual(progress_status(10, 8, 0), "remaining")
        self.assertEqual(remaining["status"], "remaining")
        self.assertIn("还差新学 16 能", remaining["title"])
        self.assertFalse(remaining["todayDone"])

        done = build_progress(
            {"cards": 0, "tasks": 0, "newEnergy": 0, "reviewEnergy": 0, "newBudget": 30, "reviewBudget": 30},
            [{"point_id": 1, "quality": 5, "correct": True, "kind": "zi"}],
            item_count=10,
        )
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["title"], "今天练完了")
        self.assertTrue(done["todayDone"])
        self.assertEqual(done["todayPracticed"], 1)
        self.assertEqual(done["todayDoneCount"], 1)
        self.assertEqual(done["todayAccuracy"], 100)

        idle = build_progress(
            {"cards": 0, "tasks": 0, "newEnergy": 0, "reviewEnergy": 0},
            [],
            item_count=10,
        )
        self.assertEqual(idle["status"], "idle")
        self.assertIn("没有要练", idle["title"])

        empty = build_progress({"cards": 0}, [], item_count=0)
        self.assertEqual(empty["status"], "empty")

    def test_parent_summary_and_weak_kinds(self):
        logs = [
            {"point_id": 1, "quality": 5, "correct": True, "kind": "zi"},
            {"point_id": 2, "quality": 1, "correct": False, "kind": "idiom"},
            {"point_id": 2, "quality": 5, "correct": True, "kind": "idiom"},
        ]
        progress = build_progress(
            {"cards": 4, "newEnergy": 8, "reviewEnergy": 0, "newBudget": 30, "reviewBudget": 30},
            logs,
            item_count=20,
            mastered=3,
            total=20,
        )
        self.assertEqual(progress["todayPracticed"], 2)
        self.assertEqual(progress["todayStreak"], 1)
        self.assertEqual(progress["weakKinds"][0]["label"], "词语")
        self.assertIn("今天已练 2 条", progress["summary"])
        self.assertIn("正确率", progress["summary"])
        self.assertIn("还差新学 8 能", progress["summary"])
        self.assertIn("已掌握 3 / 20", progress["summary"])
        sentence = parent_copy("done", 4, 75, [{"label": "易错字"}], 0, 0, mastered=1, total=8)
        self.assertIn("今天练完了", sentence)
        self.assertIn("易错字", sentence)

    def test_kid_feedback_by_mode(self):
        wrong = {"quality": 1, "correct": False, "chars": [{"char": "待", "ok": False}, {"char": "兔", "ok": True}]}
        peeked = kid_feedback("learn", wrong, revealed=True, update_sm2=True)
        self.assertEqual(peeked["title"], "看过答案了")
        self.assertIn("模糊", peeked["hint"])
        self.assertEqual(peeked["wrongChars"], [])

        failed = kid_feedback("learn", wrong, revealed=False, update_sm2=True)
        self.assertEqual(failed["title"], "这题先记下")
        self.assertIn("待", failed["hint"])
        self.assertIn("还会再练", failed["next"])

        passed = kid_feedback("test", {"quality": 5, "correct": True, "chars": []}, revealed=False)
        self.assertEqual(passed["title"], "全对！")

        recite = kid_feedback("recite", {"quality": 5, "correct": True}, revealed=False, update_sm2=False)
        self.assertEqual(recite["title"], "读得对")
        self.assertIn("不改下次", recite["hint"])

    def test_mastery_counts(self):
        counts = mastery_counts(
            [
                {"kind": "zi", "mastered": True, "last": "2026-09-01", "study_count": 2, "review_count": 1, "error_count": 0},
                {"kind": "idiom", "mastered": False, "last": "2026-09-01", "study_count": 1, "review_count": 0, "error_count": 2},
                {"kind": "zi", "mastered": False, "last": None, "study_count": 0, "review_count": 0, "error_count": 0},
            ]
        )
        self.assertEqual(counts["mastered"], 1)
        self.assertEqual(counts["learning"], 1)
        self.assertEqual(counts["unseen"], 1)
        self.assertEqual(counts["weakKinds"][0]["label"], "词语")

    def test_week_brief_and_time_cap(self):
        from datetime import date

        empty = week_brief([], today=date(2026, 9, 7))
        self.assertEqual(empty["daysPracticed"], 0)
        self.assertIn("还没练", empty["summary"])
        logs = [
            {"correct": True, "kind": "zi", "created_at": "2026-09-07T08:00:00"},
            {"correct": False, "kind": "idiom", "created_at": "2026-09-06T08:00:00"},
            {"correct": True, "kind": "idiom", "created_at": "2026-09-06T09:00:00"},
            {"correct": True, "kind": "zi", "created_at": "2026-08-01T08:00:00"},
        ]
        brief = week_brief(logs, today=date(2026, 9, 7))
        self.assertEqual(brief["daysPracticed"], 2)
        self.assertEqual(brief["attempts"], 3)
        self.assertEqual(brief["accuracy"], 67)
        self.assertEqual(brief["weakKinds"][0]["label"], "词语")
        self.assertIn("近 7 天练了 2 天", brief["summary"])
        cap = time_cap_state(16 * 60, 15)
        self.assertEqual(cap["todayMinutes"], 16)
        self.assertTrue(cap["timeCapReached"])

    def test_wizard_grade_plan(self):
        plan = wizard_plan("三年级上")
        self.assertEqual(plan["grade"], "三年级上")
        self.assertIn("zi", plan["kinds"])
        self.assertIn("L1", plan["levels"])
        self.assertEqual(plan["minutes"], 15)
        self.assertIsNone(wizard_plan("高中"))


class DemoHintTests(unittest.TestCase):
    def test_demo_hints_respect_flag_and_jwt(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"JWT_SECRET": "ccyuwen-dev"}, clear=False):
            os.environ.pop("DEMO_HINTS", None)
            self.assertTrue(demo_hints_enabled())
        with patch.dict(os.environ, {"JWT_SECRET": "prod-secret", "DEMO_HINTS": "0"}):
            self.assertFalse(demo_hints_enabled())
        with patch.dict(os.environ, {"JWT_SECRET": "prod-secret", "DEMO_HINTS": "yes"}):
            self.assertTrue(demo_hints_enabled())


if __name__ == "__main__":
    unittest.main()
