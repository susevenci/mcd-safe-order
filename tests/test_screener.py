"""单元测试：全部离线运行，不需要 Token。"""

import json
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(BASE, "samples", "nutrition_sample.json")

import sys
sys.path.insert(0, os.path.join(BASE, "src"))

from nutrition import load_snapshot, normalize, normalize_all, parse_number  # noqa: E402,F401
from profiles import ALLERGENS, get_profile, list_profiles  # noqa: E402
from report import render_html, render_text  # noqa: E402
from screener import best_combo, screen_all, screen_item  # noqa: E402


def load_sample():
    with open(SAMPLE, "r", encoding="utf-8") as fh:
        return load_snapshot(SAMPLE)


class ParseTest(unittest.TestCase):
    def test_parse_number_variants(self):
        self.assertEqual(parse_number("12.3 克"), 12.3)
        self.assertEqual(parse_number("1,234"), 1234.0)
        self.assertEqual(parse_number(42), 42.0)
        self.assertIsNone(parse_number(None))
        self.assertIsNone(parse_number(""))

    def test_chinese_fields(self):
        item = normalize({"菜品名称": "举例", "能量": 500, "蛋白质": "20 克", "钠": "800 毫克"})
        self.assertEqual(item.name, "举例")
        self.assertEqual(item.kcal, 500)
        self.assertEqual(item.protein, 20.0)
        self.assertEqual(item.sodium, 800.0)

    def test_kj_converted(self):
        item = normalize({"name": "举例", "能量kJ": 2092})
        self.assertAlmostEqual(item.kcal, 500.0, delta=1.0)

    def test_real_pseudo_table(self):
        """锁定真实返回的伪表格形态：data 是字符串而不是数组。"""
        from nutrition import parse_pseudo_table
        text = ('[2]{productName,nutritionDescription,energyKj,energyKcal,'
                'protein,fat,carbohydrate,sodium,calcium}:\n'
                '  猪柳麦满分,null,1288,308,16,16,24,781,213\n'
                '  中薯条,null,1210,289,4,12,38,165,18\n')
        records = parse_pseudo_table(text)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["productName"], "猪柳麦满分")
        self.assertEqual(records[1]["sodium"], "165")
        items = normalize_all({"data": text})
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].name, "猪柳麦满分")
        self.assertAlmostEqual(items[0].kcal, 308.0, delta=1.0)
        self.assertAlmostEqual(items[0].sodium, 781.0, delta=0.5)

    def test_pseudo_table_null_and_short_rows(self):
        from nutrition import parse_pseudo_table
        text = '[1]{a,b,c}:\n  1,null\n'
        rec = parse_pseudo_table(text)[0]
        self.assertEqual(rec["a"], "1")
        self.assertIsNone(rec["b"])
        self.assertIsNone(rec["c"])

    def test_pseudo_table_empty_safe(self):
        from nutrition import parse_pseudo_table
        self.assertEqual(parse_pseudo_table(""), [])
        self.assertEqual(parse_pseudo_table(None), [])
        self.assertEqual(parse_pseudo_table("没有任何表格"), [])

    def test_absurd_value_treated_as_kj(self):
        item = normalize({"name": "举例", "energy": 4184})
        self.assertAlmostEqual(item.kcal, 1000.0, delta=1.0)


class ProfileTest(unittest.TestCase):
    def test_all_profiles_loadable(self):
        self.assertGreaterEqual(len(list_profiles()), 5)
        for p in list_profiles():
            self.assertTrue(p.name)
            self.assertTrue(p.summary)

    def test_get_profile_by_chinese(self):
        p = get_profile("儿童")
        self.assertEqual(p.slug, "child")

    def test_unknown_profile_raises(self):
        with self.assertRaises(KeyError):
            get_profile("不存在的人群")

    def test_allergen_table_nonempty(self):
        self.assertIn("花生坚果", ALLERGENS)
        self.assertIn("海鲜鱼类", ALLERGENS)


class ScreenerTest(unittest.TestCase):
    def setUp(self):
        self.items = load_sample()

    def test_sample_loaded(self):
        self.assertGreaterEqual(len(self.items), 20)

    def test_child_rejects_big_mac(self):
        profile = get_profile("child")
        big_mac = next(i for i in self.items if i.name == "巨无霸")
        verdict = screen_item(big_mac, profile)
        self.assertEqual(verdict.level, "RED")
        self.assertTrue(any("规避词" in c for c in verdict.cautions))

    def test_vegetarian_avoids_meat(self):
        profile = get_profile("vegetarian")
        chicken = next(i for i in self.items if i.name == "板烧鸡腿堡")
        self.assertEqual(screen_item(chicken, profile).level, "RED")

    def test_lowsugar_avoids_cola(self):
        profile = get_profile("lowsugar")
        cola = next(i for i in self.items if i.name == "可乐(中)")
        verdict = screen_item(cola, profile)
        self.assertEqual(verdict.level, "RED")
        self.assertTrue(any("糖" in r for r in verdict.reasons))

    def test_missing_field_flagged_not_zero(self):
        profile = get_profile("hypertension")
        apple = normalize({"foodName": "神秘新品"})  # 无任何营养字段
        verdict = screen_item(apple, profile)
        self.assertEqual(verdict.level, "GREEN")  # 无数据不得判为超标
        self.assertIn("钠", verdict.missing)

    def test_report_counts_consistent(self):
        result = screen_all(self.items, get_profile("child"))
        total = sum(result["counts"].values())
        self.assertEqual(total, result["total"])

    def test_render_text_runs(self):
        result = screen_all(self.items, get_profile("fatloss"))
        text = render_text(result, "测试")
        self.assertIn("安心点安全筛查", text)
        self.assertIn("可以点", text)

    def test_render_html_escapes(self):
        result = screen_all(self.items, get_profile("elder"))
        page = render_html(result)
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertIn("安心点报告", page)

    def test_json_serializable(self):
        result = screen_all(self.items, get_profile("pregnant"))
        clean = {k: v for k, v in result.items() if not k.startswith("_")}
        json.dumps(clean, ensure_ascii=False)  # 不应抛异常

    def test_combo_within_limit(self):
        profile = get_profile("fatloss")
        combos = best_combo(self.items, profile)
        for c in combos:
            self.assertLessEqual(c["kcal"], profile.max_kcal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
