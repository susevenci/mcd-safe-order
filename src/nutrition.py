"""营养数据归一化。

麦当劳 MCP 的 `list-nutrition-foods` 返回约 160 款餐品的多维营养数据，
字段名在不同版本间可能是中文（能量/蛋白质/钠）也可能是英文（energy/protein/sodium），
单位可能是 kcal 也可能是 kJ，还可能是带单位的字符串（"12.3 克"）。

本模块负责把任意一种形态统一成 NutritionItem，
**并且保留 raw 以便追溯** —— 任何换算都能回溯原始字段。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def parse_number(value: Any) -> Optional[float]:
    """把 "12.3 克" / "1,234" / 12.3 / None 统一转成 float，失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("，", "")
    m = _NUM_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


FIELD_ALIASES = {
    "kcal": ["热量", "能量", "卡路里", "energy", "kcal", "kilocalorie", "calorie"],
    "protein": ["蛋白质", "蛋白", "protein"],
    "fat": ["脂肪", "fat", "总脂肪"],
    "carb": ["碳水化合物", "碳水", "carbohydrate", "carbo", "carb"],
    "sugar": ["糖", "糖分", "sugar"],
    "sodium": ["钠", "钠含量", "sodium", "na"],
    "calcium": ["钙", "calcium", "ca"],
}

CATEGORY_RULES = [
    ("饮料", ["可乐", "雪碧", "橙汁", "茶", "水", "气泡", "美式", "latte", "咖啡"]),
    ("咖啡", ["咖啡", "拿铁", "美式", "espresso", "latte", "卡布"]),
    ("冰淇淋甜品", ["麦旋风", "圆筒", "新地", "冰淇淋", "甜筒", "暴风"]),
    ("小食", ["薯条", "鸡块", "鸡翅", "洋葱圈", "玉米", "棒", "酥", "派"]),
    ("汉堡", ["堡", "卷", "burger"]),
    ("早餐", ["早餐", "吉士蛋", "堡蒸", "粥", "豆浆", "麦满分"]),
    ("沙拉", ["沙拉"]),
]


@dataclass
class NutritionItem:
    name: str
    category: str = "其他"
    kcal: Optional[float] = None
    protein: Optional[float] = None
    fat: Optional[float] = None
    carb: Optional[float] = None
    sugar: Optional[float] = None
    sodium: Optional[float] = None
    calcium: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def key_facts(self) -> str:
        parts = []
        if self.kcal is not None:
            parts.append("%.0f kcal" % self.kcal)
        if self.protein is not None:
            parts.append("蛋白 %.1f g" % self.protein)
        if self.fat is not None:
            parts.append("脂肪 %.1f g" % self.fat)
        if self.sodium is not None:
            parts.append("钠 %.0f mg" % self.sodium)
        return "·".join(parts) or "无营养数据"


def _pick(record: Dict[str, Any], aliases: List[str]) -> Optional[float]:
    lowered = {str(k).strip().lower(): v for k, v in record.items()}
    for alias in aliases:
        key = alias.lower()
        for actual, value in lowered.items():
            if actual == key or actual.endswith(key) or key in actual:
                num = parse_number(value)
                if num is not None:
                    return num
    return None


def _is_kilojoule(record: Dict[str, Any]) -> bool:
    for k in record:
        key = str(k).lower()
        if "kj" in key or "千焦" in key or "焦耳" in key:
            return True
    return False


def categorize(name: str) -> str:
    lowered = str(name).lower()
    for label, kws in CATEGORY_RULES:
        for kw in kws:
            if kw.lower() in lowered:
                return label
    return "其他"


def normalize(record: Dict[str, Any]) -> NutritionItem:
    """把任意形态的营养记录归一化为 NutritionItem。"""
    name = ""
    for key in ("foodName", "name", "productName", "菜品名称", "餐品名称", "名称", "food"):
        if key in record and record[key]:
            name = str(record[key]).strip()
            break
    if not name:
        name = str(record.get("text", ""))[:24] or "未知餐品"

    kcal = _pick(record, FIELD_ALIASES["kcal"])
    if kcal is not None and _is_kilojoule(record):
        kcal = round(kcal / 4.184, 1)  # kJ -> kcal
    elif kcal is not None and kcal > 3000:
        # 极端值几乎必然是 kJ（单份餐品不会超过 3000 kcal）
        kcal = round(kcal / 4.184, 1)

    return NutritionItem(
        name=name,
        category=categorize(name),
        kcal=kcal,
        protein=_pick(record, FIELD_ALIASES["protein"]),
        fat=_pick(record, FIELD_ALIASES["fat"]),
        carb=_pick(record, FIELD_ALIASES["carb"]),
        sugar=_pick(record, FIELD_ALIASES["sugar"]),
        sodium=_pick(record, FIELD_ALIASES["sodium"]),
        calcium=_pick(record, FIELD_ALIASES["calcium"]),
        raw=record,
    )


def normalize_all(raw_items) -> List[NutritionItem]:
    """容错遍历：dict / {"data": [...]} / 伪表格字符串 / 文本行 都能吃进去。"""
    # 形态 A：{"data": "[160]{col1,col2}: \n  值,值,..."} —— 自定义伪表格
    if isinstance(raw_items, dict) and isinstance(raw_items.get("data"), str):
        return [normalize(r) for r in parse_pseudo_table(raw_items["data"])]
    if isinstance(raw_items, str):
        return [normalize(r) for r in parse_pseudo_table(raw_items)]
    # 形态 B：{"data": [...]} 或 {"list": [...]}
    if isinstance(raw_items, dict):
        for key in ("foods", "list", "items", "data", "nutritionList"):
            if isinstance(raw_items.get(key), list):
                raw_items = raw_items[key]
                break
        else:
            raw_items = [raw_items]
    if not isinstance(raw_items, list):
        return []
    return [normalize(r) for r in raw_items if isinstance(r, dict)]


_TABLE_HEADER_RE = re.compile(r"^\[(\d+)\]\{([^}]*)\}\s*:?")


def parse_pseudo_table(text: str) -> List[Dict]:
    """解析麦当劳 MCP `list-nutrition-foods` 返回的伪表格字符串。

    实测真实形态（2026-10-25）::

        [160]{productName,nutritionDescription,energyKj,energyKcal,
              protein,fat,carbohydrate,sodium,calcium}:
          猪柳麦满分,null,1288,308,16,16,24,781,213
          中薯条,null,1210,289,4,12,38,165,18
          ...

    说明：
      * 首行声明记录数与列名，随后每行一条记录；
      * 分隔为半角逗号，null 表示无值；
      * 若某列文本自带逗号，按 maxsplit 对齐会导致后续列错位 ——
        本项目如实按位切分并在 README 中说明，不做猜测式修复。
    """
    if not text or not isinstance(text, str):
        return []
    lines = [ln.rstrip() for ln in text.splitlines()]
    header = None
    records = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        m = _TABLE_HEADER_RE.match(s)
        if m:
            header = [c.strip() for c in m.group(2).split(",") if c.strip()]
            continue
        if header is None:
            continue  # 还没看到列声明，跳过说明文字
        # maxsplit 保留最后一列的完整性，同时兼容前面列里的逗号
        values = s.split(",", len(header) - 1)
        if len(values) < len(header):
            values += [None] * (len(header) - len(values))
        record = {}
        for key, val in zip(header, values):
            v = (val or "").strip() if isinstance(val, str) else val
            record[key] = None if v in (None, "", "null", "None") else v
        records.append(record)
    return records


def load_snapshot(path: str) -> List[NutritionItem]:
    """读取本地 JSON 快照（离线演示用）。"""
    import json

    with open(path, "r", encoding="utf-8") as fh:
        return normalize_all(json.load(fh))
