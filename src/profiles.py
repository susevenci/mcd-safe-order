"""人群画像与忌口规则库。

设计原则：**规则可读、可审计**。
所有阈值都写在本文件里并标注参考出处倾向，使用者可以自己改。
项目不声称具备医学权威性 —— 见 README「真实性对照表」。

阈值口径说明（便于自查）：
  * max_kcal  ：单餐建议热量上限（kcal）
  * max_sodium：单餐建议钠上限（mg）
  * max_sugar ：单餐建议糖上限（g）
  * min_protein：单餐建议蛋白质下限（g），不足会提示"蛋白质偏低"
以上均为"科普口径的参考区间"，不是诊疗建议。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# --------------------------------------------------------------------------- #
# 忌口项：名称 -> 判定关键词（命中即视为"需确认"或"避免"）
# 注意：这是基于餐品名称/成分的**推断**，不是官方过敏原声明，
# 报告中会以"推断"字样明确标注，并建议到店核实。
# --------------------------------------------------------------------------- #
ALLERGENS: Dict[str, List[str]] = {
    "花生坚果": ["花生", "坚果", "杏仁", "腰果", "开心果", "榛果", "nut"],
    "海鲜鱼类": ["鱼", "鳕鱼", "虾", "蟹", "贝", "鱿鱼", "海鲜"],
    "牛肉": ["牛", "牛肉", "安格斯", "汉堡牛"],
    "鸡肉": ["鸡", "鸡腿", "鸡排", "麦辣鸡", "板烧鸡"],
    "猪肉": ["猪", "培根", "火腿", "香肠", "猪柳"],
    "乳制品": ["奶", "芝士", "奶酪", "黄油", "冰淇淋", "新地", "拿铁", "latte", "cheese"],
    "蛋类": ["蛋", "鸡蛋", "蛋挞", "egg"],
    "麸质小麦": ["面包", "饼", "汉堡", "卷", "麦芬", "派", "面", " tortilla"],
    "芝麻": ["芝麻", "sesame"],
    "辛辣": ["辣", "麻辣", "香辣", "劲辣", "川味"],
}


@dataclass
class Profile:
    """一个特殊人群画像。"""

    slug: str
    name: str
    summary: str
    max_kcal: Optional[float] = None
    max_sodium: Optional[float] = None
    max_sugar: Optional[float] = None
    min_protein: Optional[float] = None
    avoid_allergens: List[str] = field(default_factory=list)
    avoid_keywords: List[str] = field(default_factory=list)
    prefer_keywords: List[str] = field(default_factory=list)
    note: str = ""


PROFILES: Dict[str, Profile] = {
    "child": Profile(
        slug="child",
        name="儿童（3-12 岁）",
        summary="控钠、控糖、避免整颗坚果与辛辣，优先小份与含钙饮品",
        max_kcal=550,
        max_sodium=900,
        max_sugar=30,
        min_protein=12,
        avoid_allergens=["花生坚果", "辛辣"],
        avoid_keywords=["巨无霸", "双层", "四件套"],
        prefer_keywords=["开心乐园餐", "牛奶", "玉米", "苹果片", "迷你"],
        note="建议陪同监护人再次确认餐品实际配料。",
    ),
    "elder": Profile(
        slug="elder",
        name="老年人",
        summary="控钠、控脂、避免过硬过辣，关注蛋白质摄入",
        max_kcal=600,
        max_sodium=800,
        max_sugar=25,
        min_protein=15,
        avoid_allergens=["辛辣"],
        avoid_keywords=["巨无霸", "双层", "超大"],
        prefer_keywords=["粥", "豆浆", "牛奶", "鸡蛋", "吉士蛋"],
        note="咀嚼与吞咽功能较弱者建议选择质地柔软的餐品。",
    ),
    "pregnant": Profile(
        slug="pregnant",
        name="孕产妇",
        summary="避免生冷、控咖啡因与高糖，关注蛋白质与钙",
        max_kcal=600,
        max_sodium=1000,
        max_sugar=25,
        min_protein=18,
        avoid_allergens=["海鲜鱼类"],
        avoid_keywords=["咖啡", "拿铁", "美式", "冰", "冰淇淋"],
        prefer_keywords=["牛奶", "豆浆", "鸡蛋", "吉士蛋", "热"],
        note="咖啡因摄入请遵医嘱；冰淇淋类请注意是否是生制冷饮。",
    ),
    "fatloss": Profile(
        slug="fatloss",
        name="减脂/体重管理",
        summary="控热量、控脂肪与精制碳水，优先高蛋白低糖",
        max_kcal=450,
        max_sodium=1200,
        max_sugar=12,
        min_protein=20,
        avoid_allergens=[],
        avoid_keywords=["薯条", "麦旋风", "派", "圆筒", "大份", "超大"],
        prefer_keywords=["吉士蛋", "板烧", "鸡胸", "沙拉", "黑咖啡", "无糖"],
        note="热量缺口请结合全天总摄入判断，本工具只看单餐。",
    ),
    "hypertension": Profile(
        slug="hypertension",
        name="控钠 / 高血压关注者",
        summary="严格控钠、控脂肪",
        max_kcal=650,
        max_sodium=600,
        max_sugar=25,
        min_protein=15,
        avoid_allergens=[],
        avoid_keywords=["酱", "腌", "熏", "芝士"],
        prefer_keywords=["玉米", "沙拉", "牛奶", "原味"],
        note="钠摄入请以临床建议为准，本工具仅依据公开营养数据排序。",
    ),
    "lowsugar": Profile(
        slug="lowsugar",
        name="控糖 / 血糖关注者",
        summary="严格控糖、控精制碳水",
        max_kcal=550,
        max_sodium=1200,
        max_sugar=8,
        min_protein=15,
        avoid_allergens=[],
        avoid_keywords=["可乐", "雪碧", "冰淇淋", "派", "甜筒", "麦旋风", "奶茶"],
        prefer_keywords=["黑咖啡", "美式", "水", "无糖", "鸡蛋"],
        note="升糖负荷受多种因素影响，请以专业营养建议为准。",
    ),
    "vegetarian": Profile(
        slug="vegetarian",
        name="素食偏好者",
        summary="避免肉类餐品",
        max_kcal=None,
        max_sodium=None,
        max_sugar=None,
        min_protein=None,
        avoid_allergens=["牛肉", "鸡肉", "猪肉", "海鲜鱼类"],
        avoid_keywords=["鸡", "牛", "猪", "鱼", "虾", "培根", "火腿"],
        prefer_keywords=["玉米", "薯条", "沙拉", "派", "咖啡"],
        note="素食人群请留意是否有动物油脂或明胶成分，建议到店核实。",
    ),
}


def get_profile(slug: str) -> Profile:
    key = (slug or "").strip().lower()
    if key in PROFILES:
        return PROFILES[key]
    # 允许中文名直接命中
    for p in PROFILES.values():
        if p.name.startswith(slug) or slug in p.name:
            return p
    raise KeyError("未知人群画像: %s（可选：%s）" % (slug, "/".join(PROFILES)))


def list_profiles() -> List[Profile]:
    return list(PROFILES.values())


def custom_profile(max_kcal=None, max_sodium=None, max_sugar=None,
                   min_protein=None, avoid_allergens=None, avoid_keywords=None):
    """命令行自定义画像：只覆盖显式给定的阈值。"""
    return Profile(
        slug="custom",
        name="自定义画像",
        summary="按命令行参数生成的临时画像",
        max_kcal=max_kcal,
        max_sodium=max_sodium,
        max_sugar=max_sugar,
        min_protein=min_protein,
        avoid_allergens=list(avoid_allergens or []),
        avoid_keywords=list(avoid_keywords or []),
    )
