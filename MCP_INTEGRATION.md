# MCP_INTEGRATION.md

> 本项目实际使用了哪些麦当劳 MCP Server 的 Tool、怎么串起来的、带来了什么业务价值。
> 麦当劳 MCP Server：<https://github.com/M-China/mcd-mcp-server>

## 1. 接入方式

| 项目 | 值 |
|---|---|
| MCP Server | `mcd-mcp`（麦当劳中国官方 MCP Server） |
| 传输协议 | Streamable HTTP（JSON-RPC 2.0），兼容 SSE 响应 |
| Endpoint | `https://mcp.mcd.cn` |
| 鉴权 | `Authorization: Bearer ${MCD_MCP_TOKEN}`（仅环境变量，不入仓） |
| 客户端实现 | `src/mcp_client.py`，纯 Python 标准库，零第三方依赖 |
| 配置文件 | `mcp-config.example.json`（仅占位符，见 §5） |

握手流程：`initialize` → `notifications/initialized` → `tools/call`。
客户端内置：**滑动窗口节流**（默认 300 次/分钟，官方上限 600）、**429 指数退避**、会话 ID 复用。

## 2. 用到的 Tool

| Tool | 用途 | 本项目怎么用 |
|---|---|---|
| `list-nutrition-foods` | 一次返回约 160 款餐品的多维营养数据 | **主数据源**。能量/蛋白质/脂肪/碳水/糖/钠/钙全部来自这里，无需任何估算 |
| `query-my-account` | 积分账户 | `selfcheck` 中做连通性校验（只读、零副作用） |
| `query-meals`（可选扩展） | 门店菜单与在售价 | 计划用于「安全 + 价格」双约束，当前版本未默认调用 |
| `query-meal-detail`（可选扩展） | 单品详情（配料/规格） | 用于增强忌口推断，当前版本未默认调用 |

> **只用只读工具。** 本项目全部命令均可安全执行，不发起下单、不消耗积分、不写入账号数据。

## 3. 调用流程

```
用户：给我爸妈点餐，他们要控盐
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ ①  McdMcpClient.initialize()                              │
│     POST /  JSON-RPC "initialize"  →  会话建立            │
├───────────────────────────────────────────────────────────┤
│ ②  tools/call  list-nutrition-foods                       │
│     ← ~160 条营养记录（中/英文字段混合、单位可能是 kJ）    │
├───────────────────────────────────────────────────────────┤
│ ③  nutrition.normalize_all()                              │
│     统一单位与字段名；解析 "12.3 克" 这类带单位字符串      │
├───────────────────────────────────────────────────────────┤
│ ④  profiles.get_profile("elder")                          │
│     取出该人群的热量/钠/糖/蛋白阈值与忌口表                │
├───────────────────────────────────────────────────────────┤
│ ⑤  screener.screen_all()                                  │
│     逐条跑确定性规则 → GREEN / YELLOW / RED + 理由         │
├───────────────────────────────────────────────────────────┤
│ ⑥  report.render_text / render_html                       │
│     终端清单 或 单文件 HTML 卡片                           │
└───────────────────────────────────────────────────────────┘
```

失败处理：`tools/call` 报错时**不静默兜底**——在 stderr 打印原因并回落到离线样例，同时在报告里标注数据来源，避免把样例数据伪装成实时结果。

## 4. 业务价值

1. **把"能不能吃"变成可计算的结论**。营养数据是公开的，但没有人会为了一顿饭翻 160 行表；规则引擎把这件事压到一条命令。
2. **面向真实特殊人群**。儿童/老人/孕产/减脂/控钠/控糖/素食 7 套画像，覆盖了中国家庭最常遇到的点餐顾虑。
3. **可解释**。每条结论都带具体数值和超标百分比，不输出"建议少吃"这种废话。
4. **合规友好**。 MCP 未提供官方过敏原字段，因此过敏维度明确标注为「名称关键词推断」并提示到店核实，不越界声称权威。

## 5. 配置示例（`mcp-config.example.json`）

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer ${MCD_MCP_TOKEN}"
      }
    }
  }
}
```

仓库内**不含任何真实 Token**；`.env` 已被 `.gitignore` 排除；Token 仅通过环境变量传递。

## 附：接口实测留痕

本项目在 2026-10-25 对麦当劳 MCP 做过真实调用，完整记录（含当时账号状态、原始输出、复现命令）
见 docs/2026-10-25-实测记录.md。

实测确认的两个关键形态（代码已适配）：
1. 响应统一为 {"success":..,"code":..,"data":<业务数据>} 信封，业务数据在 data 内；
2. structuredContent 与 content[0].text 并存，客户端优先取 structuredContent。
