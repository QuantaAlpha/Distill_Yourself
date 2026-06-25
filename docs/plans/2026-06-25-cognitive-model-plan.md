# Cognitive Model Implementation Plan

> **Spec:** `docs/specs/2026-06-25-cognitive-model-spec.md`
> **Goal:** 新增 Cognitive Model 认知引擎 — 4 层流水线 + 7 维度 + Digital Twin UI tab

---

### Task 1: DB Schema — 新增 10 张表

**Files:** `db.py`

- [ ] **Step 1:** 在 `init_db()` 中新增表定义

```sql
-- L1: Episodes
CREATE TABLE IF NOT EXISTS episodes (...)
CREATE TABLE IF NOT EXISTS episode_refs (...)
-- L2: 7 维度表
CREATE TABLE IF NOT EXISTS cm_tensions (...)
CREATE TABLE IF NOT EXISTS cm_principles (...)
CREATE TABLE IF NOT EXISTS cm_tradeoffs (...)
CREATE TABLE IF NOT EXISTS cm_reasoning (...)
CREATE TABLE IF NOT EXISTS cm_communication (...)
CREATE TABLE IF NOT EXISTS cm_roles (...)
CREATE TABLE IF NOT EXISTS cm_expertise (...)
-- L3: Policies
CREATE TABLE IF NOT EXISTS cm_policies (...)
```

所有表名加 `cm_` 前缀（cognitive model），避免和现有表冲突。episodes 不加前缀因为是独立概念。

- [ ] **Step 2:** 新增 CRUD 函数

为每张表提供：`upsert_*`, `get_*`, `get_all_*`, `delete_*`
为 episodes 提供：`get_episodes_by_session`, `get_episodes_by_domain`
为 episode_refs 提供：`get_refs_for_episode`, `get_episodes_for_target`
为 cm_policies 提供：`get_active_policies`, `get_policies_by_source`

- [ ] **Step 3:** 新增统计函数

`get_twin_stats()` → 返回各表行数 + 置信度分布 + 最后更新时间

- [ ] **Step 4:** 验证

```bash
python3 -c "import db; db.init_db(); print('Tables created OK')"
```

- [ ] **Step 5:** Commit

```
feat: add cognitive model DB schema — 10 tables for 4-layer twin pipeline
```

---

### Task 2: CLI 命令 — analyze.py 扩展

**Files:** `analyze.py`

- [ ] **Step 1:** `twin-stats` 命令

显示 Cognitive Model 各表统计。调用 `db.get_twin_stats()`。

- [ ] **Step 2:** `twin-episodes` 命令

查询/列出 episodes 表，支持 `--domain`, `--signal`, `--session`, `--limit`。

- [ ] **Step 3:** `twin-dimensions` 命令

查询/列出任意 L2 维度表，`--dimension tensions|principles|...`，支持 `--status`, `--domain`, `--min-confidence`。

- [ ] **Step 4:** `twin-policies` 命令

查询/列出 policies 表，支持 `--status active|deprecated`, `--role`, `--domain`。

- [ ] **Step 5:** `twin-write` 命令（类似 evolve-write）

Agent 写入 Cognitive Model 数据的入口。接受 JSON 操作指令：
```json
{"table": "cm_principles", "operations": [
  {"action": "insert", "data": {...}},
  {"action": "update", "id": "p12", "data": {...}}
]}
```
验证 schema → 执行 SQL → 返回结果。

- [ ] **Step 6:** `twin-compile` 命令

从 L2 各维度表编译 L3 policies。纯 Python 计算：
- 从 principles 生成 IF/THEN/UNLESS 格式
- 从 tensions 生成冲突解决策略
- 从 tradeoffs 生成场景策略
- 从 communication 生成沟通规则
写入 cm_policies 表。

- [ ] **Step 7:** 注册到 argparse + 验证

```bash
python3 analyze.py twin-stats
python3 analyze.py twin-episodes --limit 5
python3 analyze.py twin-dimensions --dimension principles --status confirmed
python3 analyze.py twin-policies --status active
```

- [ ] **Step 8:** Commit

```
feat: add cognitive model CLI commands — twin-stats/episodes/dimensions/policies/write/compile
```

---

### Task 3: Server API + 分析流水线

**Files:** `server.py`

- [ ] **Step 1:** REST API endpoints

8 个 GET/POST endpoints（spec §6），路由挂在 `/api/twin/` 下。
数据从 db.py 查询，JSON 返回。

- [ ] **Step 2:** Stage 1 prompt — Episode 提取

构建 prompt 让 AI 从会话中提取结构化 episodes。
复用现有 `_collect_profile_digest` 和 corrections 数据作为信号输入。
Agent 通过 `twin-write` 写入 episodes 表。

- [ ] **Step 3:** Stage 2 prompt — 认知模型推断

构建 7 个维度各自的提取 prompt。每个 prompt 包含：
- 该维度现有条目（用于去重）
- 新的 episodes 数据
- 现有 Profile/Memory/Rules 数据作为辅助输入
Agent 通过 `twin-write` 写入对应维度表。

- [ ] **Step 4:** 分析编排 — `/api/twin/analyze`

SSE 流式端点。编排流程：
1. 检测哪些会话是新的/变更的
2. 派 Agent 执行 Stage 1（Episode 提取）
3. 等 Stage 1 完成后派 Agent 执行 Stage 2（7 维度并行）
4. Stage 2 完成后执行 Stage 3（twin-compile，纯计算）
5. 流式返回进度

- [ ] **Step 5:** Sync 端点 — `/api/twin/sync`

从 cm_policies 编译 Runtime Pack：
- 精选 top 25 active policies
- 写入 CLAUDE.md（`<!-- cognitive-model:start/end -->` marker）
- 写入 `~/.claude/memory/cognitive_*.md` 文件

- [ ] **Step 6:** 验证

```bash
curl http://localhost:5757/api/twin/overview
curl http://localhost:5757/api/twin/stats
```

- [ ] **Step 7:** Commit

```
feat: add cognitive model API + analysis pipeline — 8 endpoints, 4-stage orchestration
```

---

### Task 4: Digital Twin Tab UI

**Files:** `static/index.html`, `static/twin.js`(new), `static/app.js`, `static/style.css`

- [ ] **Step 1:** HTML 骨架

index.html 添加：
- 侧边栏第 4 个 tab 按钮（🧠 Digital Twin）
- `#twin-view` 容器（概览 + 维度详情 + 策略页）

- [ ] **Step 2:** twin.js — 概览页

7 个维度摘要卡片，从 `/api/twin/overview` 获取数据。
每张卡片：图标 + 名称 + 条目数 + 置信度条 + top 3 预览。
点击卡片 → 切换到该维度详情。

- [ ] **Step 3:** twin.js — 维度详情页

条目列表 + 排序/过滤控制。
展开后显示完整描述 + 关联条目 + 支撑 episodes。
Episodes 可点击跳转到原始会话。

- [ ] **Step 4:** twin.js — 策略页

Active policies 列表。IF/THEN/UNLESS + rationale。
点击追溯：policy → principle → episodes。

- [ ] **Step 5:** twin.js — 分析控制

Analyze 按钮 → SSE 流式显示进度（复用 evolve.js 的流式渲染模式）。
Sync 按钮 → 调用 sync API。
上次分析时间 + 变更统计。

- [ ] **Step 6:** app.js — 视图切换

接入视图切换系统，键盘快捷键 `4` 切换到 Twin 视图。

- [ ] **Step 7:** style.css — Twin 页面样式

概览卡片网格、维度详情列表、策略卡片、面包屑导航。
风格与现有 Evolve 页面一致。

- [ ] **Step 8:** 浏览器验证 + Commit

```
feat: add Digital Twin tab — overview, dimension drill-down, policy trace, analyze/sync controls
```

---

### Task 5: 端到端验证 + .knowhow 更新

- [ ] **Step 1:** 启动服务器，走通完整流程

1. 打开 Digital Twin tab
2. 点击 Analyze
3. 等待分析完成
4. 浏览各维度数据
5. 点击 Sync
6. 验证 CLAUDE.md 和 memory 文件

- [ ] **Step 2:** 创建 .knowhow/ 结构并记录

- [ ] **Step 3:** 更新 README 添加 Digital Twin 介绍

- [ ] **Step 4:** Final commit

```
docs: add cognitive model spec/plan, update README with Digital Twin feature
```
