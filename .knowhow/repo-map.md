# Repo Map

## 目录结构

```
ConvoLab/
├── server.py        # HTTP server (~3000 lines) — REST API, JSONL parser, AI proxy, SSE, Twin sync
├── db.py            # SQLite storage — sessions, messages, FTS5, aggregates, cognitive model tables
├── analyze.py       # CLI analytics (~2600 lines) — analysis + evolve generators + twin commands
├── start.sh
├── docs/
│   ├── specs/       # 设计 spec
│   ├── plans/       # 实施计划
│   └── vision.html
└── static/
    ├── index.html   # SPA shell — sidebar nav + 4 views (sessions/ai/insights/twin)
    ├── app.js       # Core app logic (~2700 lines)
    ├── evolve.js    # Evolve D3 visualizations (~1450 lines)
    ├── twin.js      # Digital Twin UI (~380 lines) — overview/drill-down/trace/policies
    └── style.css    # Styles (~1900 lines)
```

## 模块职责

### server.py
- HTTP 路由（do_GET/do_POST）
- JSONL 解析（Claude Code + Codex 双数据源）
- Evolve AI prompt 构建 + SSE 流式
- Evolve Sync（Profile→CLAUDE.md, Memory→memory/）
- **Twin API**（/api/twin/* 8 个端点）
- **Twin Sync**（policies→CLAUDE.md + memory/ cognitive_*.md）

### db.py
- SQLite WAL 模式 + 线程局部连接
- sessions/messages/FTS5/aggregates（原有）
- **Cognitive Model 10 张表**：episodes, episode_refs, cm_tensions, cm_principles, cm_tradeoffs, cm_reasoning, cm_communication, cm_roles, cm_expertise, cm_policies
- cm_upsert/cm_get/cm_get_all/cm_delete/cm_count/cm_add_ref/get_twin_stats

### analyze.py
- 15 个原有 CLI 命令（sessions/read/search/corrections/evolve-*...）
- **6 个 twin 命令**：twin-stats, twin-episodes, twin-dimensions, twin-policies, twin-write, twin-compile

### static/twin.js
- Digital Twin tab 的全部 UI 逻辑
- 概览卡片 → 维度钻取 → 条目详情+episode追溯 → 策略列表
- wiki 式面包屑导航
