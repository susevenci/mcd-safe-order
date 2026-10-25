"""mcd-safe-order 命令行入口。

零依赖，标准库即可运行。没有 Token 也能用 `--offline` 跑通全部逻辑。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_client import McpError, McdMcpClient  # noqa: E402
from nutrition import load_snapshot, normalize_all  # noqa: E402
from profiles import custom_profile, get_profile, list_profiles  # noqa: E402
from report import render_combo, render_html, render_text, result_to_json  # noqa: E402
from screener import best_combo, screen_all  # noqa: E402

OFFLINE_SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "samples", "nutrition_sample.json")


def fetch_items(offline: bool, snapshot: str = ""):
    """返回 (items, source_note)。"""
    if not offline:
        try:
            client = McdMcpClient.from_env()
            raw = client.call_tool("list-nutrition-foods")
            items = normalize_all(raw)
            if items:
                return items, "麦当劳 MCP list-nutrition-foods 实时返回（%d 款）" % len(items)
            print("[warn] 实时返回为空，自动回落到本地样例", file=sys.stderr)
        except McpError as exc:
            print("[warn] MCP 调用失败，自动回落到本地样例：%s" % exc, file=sys.stderr)
    path = snapshot or OFFLINE_SAMPLE
    items = load_snapshot(path)
    return items, "本地示例快照 %s（%d 款，非实时数据）" % (os.path.basename(path), len(items))


def build_profile(args):
    if getattr(args, "profile", None) == "custom":
        return custom_profile(
            max_kcal=args.max_kcal, max_sodium=args.max_sodium,
            max_sugar=args.max_sugar, min_protein=args.min_protein,
            avoid_allergens=(args.avoid_allergen or "").split(",") if args.avoid_allergen else [],
            avoid_keywords=(args.avoid_keyword or "").split(",") if args.avoid_keyword else [],
        )
    return get_profile(args.profile)


def cmd_profiles(_args):
    print("【可选人群画像】")
    for p in list_profiles():
        print("  %-8s %s" % (p.slug, p.name))
        print("           %s" % p.summary)
    print("\n【忌口/成分推断维度】")
    from profiles import ALLERGENS
    print("  " + "、".join(ALLERGENS.keys()))
    return 0


def cmd_selfcheck(_args):
    st = McdMcpClient.token_status()
    print("=== 环境自检 ===")
    print("MCD_MCP_TOKEN: %s" % ("已配置" if st["configured"] else "未配置"))
    print("tokenLength  : %d" % st["tokenLength"])
    print("endpoint     : %s" % st["endpoint"])
    print("结论：%s" % ("Token 已就绪，可执行真实调用"
                        if st["configured"] else "未配置 Token，可用 --offline 体验"))
    return 0


def cmd_screen(args):
    profile = build_profile(args)
    items, note = fetch_items(args.offline, getattr(args, "snapshot", ""))
    result = screen_all(items, profile, top_n=args.top)

    if args.json:
        print(result_to_json(result))
    elif args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(result, note))
        print("已生成 HTML 报告：%s" % args.html)
    else:
        print(render_text(result, note))
    return 0


def cmd_combo(args):
    profile = build_profile(args)
    items, note = fetch_items(args.offline, getattr(args, "snapshot", ""))
    combos = best_combo(items, profile, top_n=args.top)
    if args.json:
        print(json.dumps(combos, ensure_ascii=False, indent=2))
    else:
        print(note)
        print(render_combo(combos))
    return 0


def cmd_snapshot(args):
    """把实时营养数据落地为 JSON，便于离线复现与回归测试。"""
    try:
        client = McdMcpClient.from_env()
        raw = client.call_tool("list-nutrition-foods")
    except McpError as exc:
        print("拉取失败：%s" % exc, file=sys.stderr)
        return 1
    items = normalize_all(raw)
    if not items:
        print("服务端未返回结构化数据，已保存原始响应供排查", file=sys.stderr)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, ensure_ascii=False, indent=2)
        return 1
    try:
        arr = raw if isinstance(raw, list) else raw.get("list") or raw.get("data") or raw
        for key in ("foods", "list", "items", "data", "nutritionList"):
            if isinstance(raw, dict) and isinstance(raw.get(key), list):
                arr = raw[key]
                break
    except Exception:
        arr = raw
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(arr, fh, ensure_ascii=False, indent=2)
    print("已保存 %d 条营养记录 -> %s" % (len(items), args.out))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mcd-safe-order",
        description="麦麦安心点：给特殊人群的麦当劳安全点餐筛查器")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("profiles", help="列出人群画像与忌口维度").set_defaults(func=cmd_profiles)
    sub.add_parser("selfcheck", help="检查 Token 是否就绪").set_defaults(func=cmd_selfcheck)

    def add_common(p):
        p.add_argument("--profile", default="child", help="人群画像（见 profiles）")
        p.add_argument("--top", type=int, default=8, help="每档展示条数")
        p.add_argument("--offline", action="store_true", help="使用本地样例，不联网")
        p.add_argument("--snapshot", default="", help="自定义本地营养快照路径")
        p.add_argument("--json", action="store_true", help="输出结构化 JSON")
        p.add_argument("--max-kcal", type=float)
        p.add_argument("--max-sodium", type=float)
        p.add_argument("--max-sugar", type=float)
        p.add_argument("--min-protein", type=float)
        p.add_argument("--avoid-allergen", default="")
        p.add_argument("--avoid-keyword", default="")

    for name, fn, help_text in (
            ("screen", cmd_screen, "对全菜单做安全筛查"),
            ("combo", cmd_combo, "推荐阈值内的【主食+饮品】组合")):
        p = sub.add_parser(name, help=help_text)
        add_common(p)
        if name == "screen":
            p.add_argument("--html", default="", help="导出单文件 HTML 报告到指定路径")
        p.set_defaults(func=fn)

    p = sub.add_parser("snapshot", help="拉取并保存实时营养数据")
    p.add_argument("--out", default=os.path.join("output", "nutrition_snapshot.json"))
    p.set_defaults(func=cmd_snapshot)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
