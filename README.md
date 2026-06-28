<div align="center">

  <h1 align="center">ConvoLab</h1>

  <p align="center"><strong>专治 Claude Code、Codex 的"反复教不会"</strong></p>

  <p align="center" style="font-size: 14px; color: #888; max-width: 700px; margin: 10px auto;">
    🧠 <em>把你被遗忘的判断、决策和纠正，蒸馏成可复用的 AI 协作资产——让 Claude Code / Codex 不再每次从零开始。</em>
  </p>

  <p style="margin: 20px 0;">
    <a href="https://github.com/QuantaAlpha/Distill_Yourself"><img src="https://img.shields.io/github/stars/QuantaAlpha/Distill_Yourself?style=flat-square&logo=github&logoColor=white&color=yellow" /></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-00A98F.svg?style=flat-square&logo=opensourceinitiative&logoColor=white" /></a>
    <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.8+-3776AB.svg?style=flat-square&logo=python&logoColor=white" /></a>
    <a href="."><img src="https://img.shields.io/badge/Dependencies-Zero-00C853?style=flat-square" /></a>
    <a href="."><img src="https://img.shields.io/badge/Privacy-Local_First-7C3AED?style=flat-square&logo=shield&logoColor=white" /></a>
  </p>

  <p style="font-size: 16px; margin: 15px 0;">
    🌐 <a href="README.md">中文</a> | <a href="README_EN.md">English</a>
  </p>

</div>

<div align="center" style="margin: 20px 0;">
  <a href="#-quick-start">
    <img src="https://img.shields.io/badge/🚀_Quick_Start-Get_Started-4CAF50?style=flat-square&logoColor=white&labelColor=2E7D32" alt="Quick Start" />
  </a>
  <a href="docs/USER_GUIDE.md">
    <img src="https://img.shields.io/badge/📖_User_Guide-Complete_Guide-2196F3?style=flat-square&logoColor=white&labelColor=1565C0" alt="User Guide" />
  </a>
  <a href="#-citation">
    <img src="https://img.shields.io/badge/📄_Citation-Paper-FF9800?style=flat-square&logoColor=white&labelColor=F57C00" alt="Citation" />
  </a>
</div>

---

<div align="center">
  <img src="docs/images/user-guide/01-home.png" alt="ConvoLab Overview" width="90%" style="border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"/>
</div>

---

## 🎯 Why ConvoLab?

你可能已经反复教过 Claude Code / Codex：

* 不要改无关文件
* 先读现有实现再动手
* 修 bug 就修 bug，不要顺手重构
* 方案太复杂，先做最小可行修复
* 边界条件、测试、项目规范别每次都忘

问题是：**这些纠正只活在当前会话里。**

终端一关，判断、决策、偏好全部沉进本地 JSONL 日志。下次开新会话，AI 又像刚入职一样。

ConvoLab 做的事很简单：

> 把 Claude Code / Codex 的历史会话变成可搜索、可分析、可写回的协作记忆。

它不是另一个 Coding Agent，而是给现有 Agent 补上长期记忆。

```mermaid
flowchart LR
    A[对话记录] --> B[浏览检索]
    B --> C[洞察分析]
    C --> D[进化引擎]
    D --> E[认知手册]
    E --> F[写回配置]
    F -.->|下次会话自动受益| A
```

---

## 🚀 Quick Start

零依赖。Python 3.8+ 即可。

```bash
git clone https://github.com/QuantaAlpha/ConvoLab.git
cd ConvoLab
python3 server.py        # → http://localhost:5757
```

自动扫描本地会话目录：

```text
~/.claude/projects/          # Claude Code
~/.codex/sessions/           # Codex
~/.codex/archived_sessions/  # Codex (archived)
```

浏览、搜索、洞察开箱即用。AI Chat、Evolve 和认知手册需要本机装有 Claude Code 或 Codex CLI（直接调用本地 CLI，不需要 API key）。

---

## ✨ Core Features

| 功能 | 解决什么 |
|---|---|
| **Session Browser** | 把分散的会话集中起来，搜索、筛选、结构化回放 |
| **Insights** | 工具热力图、文件热点、重复错误、项目活跃度 |
| **Evolve** | 从反复纠正中提炼可复用的偏好和行为规则 |
| **Cognitive Handbook** | 把零散纠正蒸馏为结构化的 Judgment Cards |
| **Preview & Sync** | 预览确认后写回 `CLAUDE.md` / `memory/`，下次会话生效 |

---

## 🔄 从"反复纠正"到"可复用记忆"

普通记忆：

```text
用户喜欢简洁代码。
```

ConvoLab 提炼的是可执行的协作判断：

```text
当 AI 修复局部 bug 时，
优先做最小必要修改，不要为了整洁顺手扩大 diff；
除非相邻代码本身就是根因。
```

这些来自真实会话中的纠正、拒绝、追问和修复过程——不是手写标签。

<div align="center">
  <img src="docs/images/user-guide/04-evolve-memory.jpg" alt="Evolve memory" width="90%" style="border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"/>
</div>

---

## 🧠 认知手册：不只记规则，还记你为什么这样判断

ConvoLab 的核心不是保存聊天记录，而是提炼协作判断。

比如你多次说过：

* "不要改无关文件"
* "先看现有代码"
* "太复杂了，简化"
* "不要把局部修复变成大重构"

ConvoLab 会把它们整理成一张 Judgment Card：

```text
触发场景：AI 正在修复局部 bug，但开始修改相邻模块。
判断逻辑：用户倾向保护最小影响范围——额外改动增加 review 成本和回归风险。
行动倾向：先完成请求范围内的最小修复。
例外边界：若相邻模块确实是根因，先说明原因，再请求扩大 scope。
```

这比"用户喜欢小改动"有用得多。下次 AI 面对新任务时，复用的是你的判断逻辑，而不是机械匹配关键词。

---

## 📝 写回 AI：让下次真的少教一遍

确认过的记忆可以写回 Claude Code 的上下文：

```text
~/.claude/CLAUDE.md      ← Profile + Cognitive Runtime Pack
~/.claude/memory/        ← Memory Cards
```

写回前必须预览，不会自动污染全局配置。

| 输出 | 写到哪里 | 是否自动 |
|---|---|---|
| Profile | `CLAUDE.md` 标记区域 | 需确认 |
| Memory Cards | `~/.claude/memory/` | 需确认 |
| Cognitive Runtime Pack | `CLAUDE.md` 标记区域 | 需确认 |
| Rules / Signals / Patterns | 仅展示，不写回 | — |

---

## 📊 Screenshots

<div align="center">
  <img src="docs/images/user-guide/02-session.jpg" alt="Session browser" width="90%" style="border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin: 10px 0;"/>
  <p style="font-size: 12px; color: #666;">Session Browser：结构化会话回放 + 大纲 + AI Chat</p>
</div>

<div align="center">
  <img src="docs/images/user-guide/05-heatmap.jpg" alt="Tool heatmap" width="90%" style="border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin: 10px 0;"/>
  <p style="font-size: 12px; color: #666;">Tool Heatmap：各类工具逐日使用强度</p>
</div>

<div align="center">
  <img src="docs/images/user-guide/06-profile-radar.png" alt="Profile radar" width="90%" style="border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin: 10px 0;"/>
  <p style="font-size: 12px; color: #666;">Profile Radar：多维能力评估 + 证据链</p>
</div>

---

<details>
<summary><b>⌨️ CLI Usage</b></summary>

```bash
# 基础查询
python3 analyze.py sessions --source claude --date 7d --limit 20
python3 analyze.py search "authentication bug" --project my-app
python3 analyze.py read abc123
python3 analyze.py corrections --date 30d
python3 analyze.py decisions --date 30d
python3 analyze.py files --date 30d
```

```bash
# Evolve
python3 analyze.py evolve-rules
python3 analyze.py evolve-signals
python3 analyze.py evolve-patterns
python3 analyze.py aggregates
python3 analyze.py profile-digest
```

```bash
# Cognitive Handbook
python3 analyze.py twin-stats
python3 analyze.py twin-events --signal correction --limit 50
python3 analyze.py twin-cards --status confirmed
python3 analyze.py twin-traits --category decision-style
python3 analyze.py twin-search "minimal fix" --limit 20
python3 analyze.py twin-compile --run-id latest
```

所有命令支持 `--json`、`--source`、`--date`、`--project`、`--limit`。

</details>

<details>
<summary><b>⚙️ Configuration & Architecture</b></summary>

```bash
PORT=3000 python3 server.py   # 默认 5757
```

```text
ConvoLab/
├── server.py          # HTTP server, REST API, JSONL parser, AI proxy, SSE
├── db.py              # SQLite, FTS5 search, cognitive model tables
├── analyze.py         # CLI analytics, Evolve, Twin operations
├── start.sh
├── docs/
│   └── USER_GUIDE.md
└── static/
    ├── index.html     # SPA shell
    ├── app.js         # Core logic
    ├── evolve.js      # Evolve visualizations
    ├── twin.js        # Cognitive Handbook UI
    └── style.css
```

| Source | Location | Format |
|---|---|---|
| Claude Code | `~/.claude/projects/` | JSONL |
| Codex | `~/.codex/sessions/` | JSONL |
| Codex (archived) | `~/.codex/archived_sessions/` | JSONL |

</details>

<details>
<summary><b>🏗️ Design Principles</b></summary>

| Principle | Implementation |
|---|---|
| **Local-first** | 只读取本机会话，不联网 |
| **Zero install** | Python stdlib + vanilla JS，无外部依赖 |
| **Evidence-backed** | 每条记忆和卡片保留原始证据链 |
| **Preview-first** | 写回前必须预览确认 |
| **Model-agnostic** | 以自然语言写入上下文，不依赖特定模型内部状态 |

</details>

---

## 🔒 Privacy

所有索引、搜索、分析和写回都在本地完成。会话数据只从本机读取，不上传到任何外部服务。前端从 D3 CDN 加载可视化库（不传输会话内容）。需要完全离线可将 D3 vendored 到 `static/`。

---

## 📄 Citation

```
Distill Yourself: From AI Coding Sessions to Digital-Twin Memory for Self-Evolving Agents
```

核心思想：用户纠正是隐式监督；反复纠正背后，是可被 AI 复用的情境化判断。

---

## 🤝 Contributing

We welcome contributions!

<a href="https://github.com/QuantaAlpha/Distill_Yourself/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=QuantaAlpha/Distill_Yourself" />
</a>

- **🐛 Bug Reports**: [Open an issue](https://github.com/QuantaAlpha/Distill_Yourself/issues)
- **💡 Feature Requests**: [Start a discussion](https://github.com/QuantaAlpha/Distill_Yourself/discussions)
- **🔧 Code Contributions**: Submit PRs for fixes, improvements, or new features

---

## License

This project is licensed under the [MIT License](LICENSE).
