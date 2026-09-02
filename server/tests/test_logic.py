"""核心逻辑自检，不连数据库。"""
import unittest

from app.cards import parse_import, validate_card
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
        self.assertIsNone(validate_card("idiom", "意思", "守株待兔"))

    def test_csv_import(self):
        parsed = parse_import(
            "kind,level,prompt,answer,tags,source\npoem,L3,欲穷千里目，______。,更上一层楼,名句,真题"
        )
        self.assertEqual(len(parsed["ok"]), 1)
        self.assertEqual(parsed["ok"][0]["answer"], "更上一层楼")

    def test_skip_empty(self):
        self.assertEqual(parse_import("[{}]")["skip"], 1)
        self.assertEqual(parse_import("")["ok"], [])


if __name__ == "__main__":
    unittest.main()
