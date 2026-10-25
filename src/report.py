"""报告渲染：终端文本 + 可分享的单文件 HTML 卡片。

HTML 采用纯手写内联 CSS、无外部字体/CDN 依赖，
生成的单个 .html 文件可以直接丢到 GitHub Pages 或发给别人。
"""

from __future__ import annotations

import html
import json
from typing import Dict, List

LEVEL_COLOR = {"GREEN": "#18a058", "YELLOW": "#f0a020", "RED": "#d03050"}


# --------------------------------------------------------------------------- #
# 终端文本
# --------------------------------------------------------------------------- #
def render_text(result: Dict, source_note: str = "") -> str:
    prof = result["profile"]
    total = result.get("total", 0)
    # 普遍缺失的字段（≥60% 记录都缺）只提示一次，不在每条下面重复刷屏
    global_missing = []
    for field_name, count in (result.get("missingByField") or {}).items():
        if total and count >= 0.6 * total:
            global_missing.append("%s（%d/%d 款均无该字段）" % (field_name, count, total))

    lines = []
    lines.append("【%s · 安心点安全筛查】" % prof["name"])
    lines.append("画像说明：%s" % prof["summary"])
    th = result["thresholds"]
    guard = []
    if th["maxKcal"]:
        guard.append("热量≤%g kcal" % th["maxKcal"])
    if th["maxSodium"]:
        guard.append("钠≤%g mg" % th["maxSodium"])
    if th["maxSugar"]:
        guard.append("糖≤%g g" % th["maxSugar"])
    if th["minProtein"]:
        guard.append("蛋白≥%g g" % th["minProtein"])
    lines.append("判定阈值：%s" % ("，".join(guard) or "未设置阈值"))
    lines.append("共筛查 %d 款：✅ 可以点 %d　⚠️ 注意着点 %d　🚫 先别点 %d" % (
        result["total"], result["counts"]["GREEN"],
        result["counts"]["YELLOW"], result["counts"]["RED"]))
    if result["missingFields"]:
        lines.append("（其中 %d 项营养字段服务端未返回，已标注为缺失而非 0）" % result["missingFields"])
    if global_missing:
        lines.append("⚠ 以下维度在实时返回中普遍缺失，已不再逐条重复：%s" % "；".join(global_missing))
    if source_note:
        lines.append("数据来源：%s" % source_note)

    def _block(title: str, rows: List[Dict], emoji: str):
        lines.append("")
        lines.append("%s %s（显示前 %d）" % (emoji, title, len(rows)))
        if not rows:
            lines.append("  —无—")
            return
        for r in rows:
            lines.append("  · %s｜%s｜%s" % (r["name"], r["levelLabel"], r["facts"]))
            for reason in r["reasons"]:
                lines.append("      - %s" % reason)
            for c in r["cautions"]:
                lines.append("      - %s" % c)
            per_item = [m for m in r["missing"]
                        if not any(m in g for g in global_missing)]
            if per_item:
                lines.append("      - 数据缺失：%s" % "、".join(per_item))

    _block("可以点", result["recommended"], "✅")
    _block("注意着点", result["caution"], "⚠️")
    _block("先别点", result["avoid"], "🚫")
    lines.append("")
    lines.append("提示：过敏原判定基于餐品名称关键词推断，请以麦当劳官方配料说明为准。")
    return "\n".join(lines)


def render_combo(combos: List[Dict]) -> str:
    if not combos:
        return "未找到满足该画像阈值的组合（放宽阈值或换个人群试试）。"
    lines = ["【组合推荐：主食 + 饮品，均在阈值内】"]
    for i, c in enumerate(combos, 1):
        lines.append("%d. %s + %s｜合计 %.0f kcal｜钠 %.0f mg｜蛋白 %.1f g" % (
            i, c["main"], c["drink"], c["kcal"], c["sodium"], c["protein"]))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# HTML 卡片
# --------------------------------------------------------------------------- #
_CSS = """
:root{color-scheme:light}
body{margin:0;padding:24px;background:#f5f6f8;color:#1f2228;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:760px;margin:0 auto;background:#fff;border-radius:16px;
padding:28px 32px;box-shadow:0 6px 24px rgba(0,0,0,.06)}
h1{margin:0 0 4px;font-size:22px}
.sub{color:#6b7280;font-size:13px;margin-bottom:18px}
.stats{display:flex;gap:12px;margin:16px 0 22px}
.stat{flex:1;border-radius:12px;padding:12px 14px;background:#f7f8fa;text-align:center}
.stat b{display:block;font-size:22px}
.stat span{font-size:12px;color:#6b7280}
.sec{margin-top:18px}
.sec h2{font-size:15px;margin:0 0 8px}
.row{border:1px solid #ececec;border-radius:10px;padding:10px 12px;margin-bottom:8px}
.row .nm{font-weight:600}
.row .meta{font-size:12px;color:#6b7280;margin-top:2px}
.row ul{margin:6px 0 0;padding-left:18px;font-size:12px;color:#4b5563}
.badge{float:right;font-size:12px;padding:2px 8px;border-radius:999px;color:#fff}
footer{margin-top:22px;font-size:12px;color:#9aa0a6;border-top:1px dashed #e5e7eb;padding-top:12px}
"""


def render_html(result: Dict, source_note: str = "") -> str:
    prof = result["profile"]
    h = html.escape
    parts = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>%s · 麦当劳安心点报告</title><style>%s</style></head><body><div class='wrap'>" % (
            h(prof["name"]), _CSS),
        "<h1>%s · 麦当劳安心点报告</h1>" % h(prof["name"]),
        "<div class='sub'>%s</div>" % h(prof["summary"]),
        "<div class='stats'>",
    ]
    for label, key, color in (("可以点", "GREEN", "#18a058"),
                              ("注意着点", "YELLOW", "#f0a020"),
                              ("先别点", "RED", "#d03050")):
        parts.append("<div class='stat'><b style='color:%s'>%d</b><span>%s</span></div>" % (
            color, result["counts"][key], label))
    parts.append("</div>")

    def rows_html(title, rows):
        out = ["<div class='sec'><h2>%s</h2>" % h(title)]
        if not rows:
            out.append("<div class='row'>无</div>")
        for r in rows:
            out.append(
                "<div class='row'><span class='badge' style='background:%s'>%s</span>"
                "<div class='nm'>%s</div><div class='meta'>%s</div>"
                % (LEVEL_COLOR.get(r["level"], "#666"), h(r["levelLabel"]),
                   h(r["name"]), h(r["facts"])))
            bullets = [x for x in r["reasons"] + r["cautions"]]
            if r["missing"]:
                bullets.append("数据缺失：%s" % "、".join(r["missing"]))
            if bullets:
                out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % h(b) for b in bullets))
            out.append("</div>")
        out.append("</div>")
        return "".join(out)

    parts.append(rows_html("✅ 可以点", result["recommended"]))
    parts.append(rows_html("⚠️ 注意着点", result["caution"]))
    parts.append(rows_html("🚫 先别点", result["avoid"]))

    note = h(source_note or "离线示例快照")
    parts.append(
        "<footer>共筛查 %d 款餐品。过敏原判定基于餐品名称关键词推断，请以麦当劳官方配料说明为准；"
        "营养口径参考《中国食物成分表》常见 NRV 参考值，不构成医疗或营养处方建议。<br>数据来源：%s</footer>"
        % (result["total"], note))
    parts.append("</div></body></html>")
    return "".join(parts)


def result_to_json(result: Dict) -> str:
    """去掉内部对象后导出 JSON。"""
    clean = {k: v for k, v in result.items() if not k.startswith("_")}
    return json.dumps(clean, ensure_ascii=False, indent=2)
