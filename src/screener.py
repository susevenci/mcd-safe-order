"""安全餐筛选引擎。

核心产出是三档结论：

  * GREEN  「可以点」—— 未命中任何禁用规则，且营养指标在画像阈值内
  * YELLOW 「注意着点」—— 某项营养略超阈值（≤25%）或存在需留意成分
  * RED    「先别点」  —— 命中忌口/禁用词，或某项营养严重超出（>25%）

诚实性三条红线（README 的「真实性对照表」会重申）：
  1. 过敏原来自**餐品名称关键词推断**，不是官方过敏原声明；
  2. 营养数据缺失时明确标注"数据缺失"，绝不假装为零；
  3. 不做医疗建议，只是把公开营养数据按规则排一遍。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from nutrition import NutritionItem
from profiles import ALLERGENS, Profile

GREEN, YELLOW, RED = "GREEN", "YELLOW", "RED"
_LABEL = {GREEN: "可以点", YELLOW: "注意着点", RED: "先别点"}
_SEV = {GREEN: 0, YELLOW: 1, RED: 2}


@dataclass
class Verdict:
    item: NutritionItem
    level: str
    score: float
    reasons: List[str] = field(default_factory=list)
    cautions: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)

    @property
    def level_label(self) -> str:
        return _LABEL.get(self.level, self.level)

    def as_dict(self) -> Dict:
        return {
            "name": self.item.name,
            "category": self.item.category,
            "level": self.level,
            "levelLabel": self.level_label,
            "score": round(self.score, 2),
            "facts": self.item.key_facts,
            "reasons": self.reasons,
            "cautions": self.cautions,
            "missing": self.missing,
        }


def _keywords_hit(text: str, keywords: List[str]) -> List[str]:
    lowered = str(text).lower()
    return [k for k in keywords if k and str(k).lower() in lowered]


def allergen_hits(name: str, profile: Profile) -> Dict[str, List[str]]:
    """返回 {忌口类型: [命中的关键词]}。"""
    hits = {}
    for allergen in profile.avoid_allergens:
        kws = ALLERGENS.get(allergen, [allergen])
        matched = _keywords_hit(name, kws)
        if matched:
            hits[allergen] = matched
    return hits


def _check_nutrient(item: NutritionItem, profile: Profile, v: Verdict):
    """检查热量 / 钠 / 糖 / 蛋白，超标或缺失都记下来。"""
    specs = [
        ("kcal", item.kcal, profile.max_kcal, "热量", "kcal"),
        ("sodium", item.sodium, profile.max_sodium, "钠", "mg"),
        ("sugar", item.sugar, profile.max_sugar, "糖", "g"),
    ]
    for key, value, cap, label, unit in specs:
        if cap is None:
            continue
        if value is None:
            v.missing.append(label)
            continue
        if value > cap:
            over = (value - cap) / cap
            msg = "%s %.1f%s，超出画像上限 %.1f%s（+%.0f%%）" % (
                label, value, unit, cap, unit, over * 100)
            if over > 0.25:
                v.reasons.append(msg + "，明显超标")
                v.level = RED
                v.score += 30 + min(30, over * 40)
            else:
                v.cautions.append(msg)
                v.level = max(v.level, YELLOW, key=_SEV.get)
                v.score += 10 + over * 20

    if profile.min_protein is not None:
        if item.protein is None:
            v.missing.append("蛋白质")
        elif item.protein < profile.min_protein:
            v.cautions.append("蛋白质 %.1f g，低于画像建议 %.1f g" % (
                item.protein, profile.min_protein))
            v.level = max(v.level, YELLOW, key=_SEV.get)
            v.score += (profile.min_protein - item.protein) * 1.5


def screen_item(item: NutritionItem, profile: Profile) -> Verdict:
    v = Verdict(item=item, level=GREEN, score=0.0)

    # 1) 忌口：名称推断
    for allergen, matched in allergen_hits(item.name, profile).items():
        v.reasons.append("疑似含「%s」类成分（命中词：%s，来自名称推断）" % (
            allergen, "、".join(matched)))
        v.level = RED
        v.score += 60

    # 2) 显式禁用词（巨无霸/薯条等由画像给出）
    hit = _keywords_hit(item.name, profile.avoid_keywords)
    if hit:
        v.cautions.append("命中画像规避词：%s" % "、".join(hit))
        v.level = RED
        v.score += 45

    # 3) 营养阈值
    _check_nutrient(item, profile, v)

    # 4) 推荐词给负分（更安全则更容易被推荐）
    bonus = _keywords_hit(item.name, profile.prefer_keywords)
    if bonus:
        v.score -= 12 * len(bonus)
        v.cautions.append("命中推荐词：%s" % "、".join(bonus))

    v.score = max(0.0, v.score)
    return v


def screen_all(items: List[NutritionItem], profile: Profile,
               top_n: int = 8) -> Dict:
    verdicts = [screen_item(it, profile) for it in items]
    buckets = {GREEN: [], YELLOW: [], RED: []}
    for v in verdicts:
        buckets[v.level].append(v)
    for level in buckets:
        buckets[level].sort(key=lambda x: (x.score, -(x.item.kcal or 0)))

    missing_total = sum(len(v.missing) for v in verdicts)
    missing_by_field: Dict[str, int] = {}
    for v in verdicts:
        for field_name in v.missing:
            missing_by_field[field_name] = missing_by_field.get(field_name, 0) + 1
    return {
        "profile": {"slug": profile.slug, "name": profile.name, "summary": profile.summary},
        "thresholds": {
            "maxKcal": profile.max_kcal,
            "maxSodium": profile.max_sodium,
            "maxSugar": profile.max_sugar,
            "minProtein": profile.min_protein,
        },
        "total": len(verdicts),
        "counts": {lv: len(buckets[lv]) for lv in (GREEN, YELLOW, RED)},
        "missingFields": missing_total,
        "missingByField": missing_by_field,
        "recommended": [v.as_dict() for v in buckets[GREEN][:top_n]],
        "caution": [v.as_dict() for v in buckets[YELLOW][:top_n]],
        "avoid": [v.as_dict() for v in buckets[RED][:top_n]],
        "_buckets": buckets,
    }


def best_combo(items: List[NutritionItem], profile: Profile, top_n: int = 3):
    """在 GREEN 档里做一次简单的「主食 + 饮品」组合推荐（纯遍历，无外部依赖）。"""
    verdicts = [v for v in (screen_item(i, profile) for i in items) if v.level == GREEN]
    mains = [v for v in verdicts if v.item.category in ("汉堡", "早餐")]
    drinks = [v for v in verdicts if v.item.category in ("饮料", "咖啡")]
    combos = []
    for m in mains:
        for d in (drinks or [None]):
            kcal = (m.item.kcal or 0) + ((d.item.kcal if d else 0) or 0)
            if profile.max_kcal and kcal > profile.max_kcal:
                continue
            sodium = (m.item.sodium or 0) + ((d.item.sodium if d else 0) or 0)
            if profile.max_sodium and sodium > profile.max_sodium:
                continue
            combos.append({
                "main": m.item.name,
                "drink": d.item.name if d else "不配饮品",
                "kcal": round(kcal, 1),
                "sodium": round(sodium, 1),
                "protein": round((m.item.protein or 0) + ((d.item.protein if d else 0) or 0), 1),
                "score": round(m.score + (d.score if d else 0), 2),
            })
    combos.sort(key=lambda c: (c["score"], c["kcal"]))
    return combos[:top_n]
