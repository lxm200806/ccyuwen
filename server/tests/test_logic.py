"""核心逻辑自检，不连数据库。"""
import unittest

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
from app.grade import grade_answer, normalize
from app.sm2 import add_days, is_mastered, schedule


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
        from app.materials import PACKS, bundled_md, dump_pack, find_pack, load_pack, read_original

        spec = find_pack("grade3-shang")
        original = read_original(spec) or bundled_md(spec).read_text(encoding="utf-8")
        self.assertIn("日积月累", original)
        self.assertGreater(len(original), 200)
        pack = load_pack(spec)
        self.assertIn("日积月累", pack["original"])
        self.assertEqual(len(pack["points"]), 40)
        parsed = parse_import(dump_pack(pack))
        self.assertEqual(len(parsed["ok"]), 40)
        self.assertEqual(parsed["ok"][0]["key"], pack["points"][0]["key"])

        keys = []
        self.assertEqual(len(PACKS), 12)
        for spec in PACKS:
            loaded = load_pack(spec)
            self.assertIn("日积月累", loaded["original"], spec["slug"])
            self.assertGreater(len(loaded["points"]), 15, spec["slug"])
            keys.extend(point["key"] for point in loaded["points"])
            for point in loaded["points"]:
                error = validate_card(point["kind"], point["prompt"], point["answer"])
                self.assertIsNone(error, point["key"] + " " + str(error))
        self.assertEqual(len(keys), len(set(keys)))

    def test_original_lists_are_in_points(self):
        import re

        from app.grade import normalize
        from app.materials import PACKS, read_original

        word_re = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
        missing = []
        for spec in PACKS:
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
                if "WHERE point_key" in text and text.strip().startswith("SELECT"):
                    self.result = next((row for row in self.rows.values() if row["point_key"] == args[0]), None)
                elif "WHERE prompt" in text:
                    self.result = next(
                        (row for row in self.rows.values() if row["prompt"] == args[0] and row["answer"] == args[1]),
                        None,
                    )
                elif text.strip().startswith("UPDATE"):
                    row = self.rows[args[-1]]
                    row.update(
                        {
                            "kind": args[0],
                            "level": args[1],
                            "grade": args[2],
                            "prompt": args[3],
                            "answer": args[4],
                            "tags": args[5],
                            "source": args[6],
                            "source_resource_id": args[7],
                            "point_key": args[8],
                            "group_key": args[9],
                            "sub_group_key": args[10],
                        }
                    )
                    self.result = {"id": row["id"]}
                elif text.strip().startswith("INSERT"):
                    point_id = self.next_id
                    self.next_id += 1
                    self.rows[point_id] = {
                        "id": point_id,
                        "kind": args[0],
                        "level": args[1],
                        "grade": args[2],
                        "prompt": args[3],
                        "answer": args[4],
                        "tags": args[5],
                        "source": args[6],
                        "source_resource_id": args[7],
                        "point_key": args[8],
                        "group_key": args[9],
                        "sub_group_key": args[10],
                    }
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
            self.assertEqual(loaded["version"], stored.get("version") or loaded["version"])


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
        self.assertEqual(len(culture), 4)
        self.assertEqual(len(art), 12)
        self.assertEqual(len({point["group_key"] for point in culture}), 1)
        self.assertEqual(len({point["group_key"] for point in art}), 1)
        self.assertNotEqual(culture[0]["group_key"], art[0]["group_key"])
        poem = next(point for point in pack["points"] if point["kind"] == "poem")
        self.assertEqual(poem["group_key"], poem["key"])

    def test_shared_source_splits_by_theme(self):
        from app.materials import find_pack, load_pack

        pack = load_pack(find_pack("grade3-xia"))
        yuyan = [point for point in pack["points"] if point["tags"] == "成语;寓言"]
        bazi = [point for point in pack["points"] if point["tags"] == "成语;八字"]
        self.assertGreaterEqual(len(yuyan), 2)
        self.assertGreaterEqual(len(bazi), 2)
        self.assertEqual(len({point["group_key"] for point in yuyan}), 1)
        self.assertEqual(len({point["group_key"] for point in bazi}), 1)
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
        self.assertEqual(left["group_key"], right["group_key"])
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
        self.assertEqual(custom["group_key"], "g1-custom")
        self.assertEqual(custom["sub_group_key"], "g2-a")

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


class EnergyTests(unittest.TestCase):
    def test_point_energy_by_kind(self):
        self.assertEqual(point_energy({"kind": "zi", "answer": "己"}), 1)
        self.assertEqual(point_energy({"kind": "idiom", "answer": "春风", "tags": "词语"}), 2)
        self.assertEqual(point_energy({"kind": "idiom", "answer": "高山流水", "tags": "成语;艺术"}), 4)
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


if __name__ == "__main__":
    unittest.main()
