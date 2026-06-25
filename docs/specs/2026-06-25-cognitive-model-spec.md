# Cognitive Model — 数字分身认知引擎 设计 Spec

**Status:** draft
**Date:** 2026-06-25
**Decision:** 4 层流水线 + L2 内含 7 认知维度，独立于现有 Evolve 5 tabs

## 1. 问题

现有 Evolve 的 Profile（描述性事实）+ Memory（孤立的 trigger/instruction 规则）= 简历 + 便签纸。
AI 知道「不该做什么」，但不知道为什么，遇到新场景只能机械遵守或瞎猜。

缺失的是**因果连接层**——从「发生了什么」到「你怎么想」到「所以该怎么做」的推理链。

## 2. 设计原则

- **现有模块不动**：Profile/Memory/Rules/Signals/Patterns 保持原样
- **Cognitive Model 独立**：独立数据表、独立 API、独立 UI tab
- **可消费现有数据**：复用 Profile/Memory/Rules 作为输入源之一
- **增量更新**：每次分析只处理新数据，写入前查历史做语义去重
- **4 层流水线**：每层独立存储、独立可重跑

## 3. 架构总览

```
原始 JSONL → Stage 1 → Stage 2 → Stage 3 → Stage 4
             Episodes   Cognitive   Policies   Runtime
             (AI提取)    Model       (纯计算)    Pack
                        (AI推断)               (纯计算)
                 ↓          ↓          ↓          ↓
              SQLite     SQLite     SQLite    文件系统
```

### 3.1 Layer 1: Evidence & Episodes

原始对话中的结构化事件记录。

**数据来源**：JSONL 会话日志（通过 AI 提取）
**存储**：SQLite `episodes` 表
**去重键**：`session_id + event_index`
**增量策略**：按 session file_mtime 判断是否需要重新提取

字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 自动生成 |
| session_id | TEXT FK | 来源会话 |
| event_index | INTEGER | 会话内事件序号 |
| task_type | TEXT | coding/review/design/research/communication |
| ai_action | TEXT | AI 做了什么 |
| user_reaction | TEXT | 用户怎么反应（correction/acceptance/escalation/rewrite） |
| resolution | TEXT | 最终结果 |
| lesson | TEXT | 提炼的教训 |
| signal_type | TEXT | correction/acceptance/question/escalation |
| signal_intensity | REAL | 0-1，纠正强度 |
| domain | TEXT | 所属领域标签 |
| created_at | TEXT | ISO timestamp |

**预计规模**：500-2000+ 条，持续累积。

### 3.2 Layer 2: Cognitive Model（7 个维度）

从 episodes 中提炼的认知模型，7 个维度各自独立存储。

#### 维度 1: Value Hierarchy（价值层级）

排序的价值张力，不是扁平标签。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | t1, t2... |
| value_a | TEXT | 张力的一端 |
| value_b | TEXT | 张力的另一端 |
| default_resolution | TEXT | 默认倾向保护哪一端 |
| context_overrides | TEXT (JSON) | 例外情况列表 |
| confidence | REAL | 0-1 |
| episode_count | INTEGER | 支撑的 episode 数量 |
| status | TEXT | hypothesis/emerging/confirmed |
| updated_at | TEXT | |

**预计规模**：30-60 条。

#### 维度 2: Causal Principles（因果原则）

连接价值观和规则的因果链。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | p1, p2... |
| statement | TEXT | 原则陈述 |
| cause | TEXT | 因（为什么） |
| effect | TEXT | 果（所以怎样） |
| domain | TEXT | 适用领域 |
| tension_ids | TEXT (JSON) | 关联的 tension |
| confidence | REAL | 0-1 |
| status | TEXT | hypothesis/emerging/confirmed/rejected |
| episode_count | INTEGER | |
| updated_at | TEXT | |

**预计规模**：60-150 条。

#### 维度 3: Tradeoff Matrix（权衡矩阵）

不同场景下保护什么、牺牲什么。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | |
| context | TEXT | 触发场景 |
| protect | TEXT (JSON) | 保护的价值列表 |
| sacrifice | TEXT (JSON) | 可牺牲的价值列表 |
| strategy | TEXT | 执行策略 |
| confidence | REAL | |
| episode_count | INTEGER | |
| updated_at | TEXT | |

**预计规模**：20-40 条。

#### 维度 4: Reasoning Style（推理风格）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | |
| dimension | TEXT | 维度名（如 evidence_first, bottom_up） |
| description | TEXT | 描述 |
| evidence | TEXT (JSON) | 支撑证据 |
| confidence | REAL | |
| updated_at | TEXT | |

**预计规模**：8-15 条（维度稳定，主要是精化描述）。

#### 维度 5: Communication Contract（沟通契约）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | |
| category | TEXT | must_do/must_avoid/must_verify |
| description | TEXT | 具体要求 |
| domain | TEXT | 适用领域（all/coding/review/...） |
| confidence | REAL | |
| episode_count | INTEGER | |
| updated_at | TEXT | |

**预计规模**：15-30 条。

#### 维度 6: Role Modes（角色模式）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | |
| role | TEXT | architect/debugger/reviewer/writer/researcher |
| behavior_profile | TEXT | 该角色下的行为模式描述 |
| key_preferences | TEXT (JSON) | 该角色下的关键偏好 |
| autonomy_level | TEXT | high/medium/low |
| confidence | REAL | |
| episode_count | INTEGER | |
| updated_at | TEXT | |

**预计规模**：5-10 条。

#### 维度 7: Domain Expertise Map（领域知识图谱）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | |
| domain | TEXT | 领域名 |
| depth | TEXT | expert/proficient/familiar/novice |
| session_count | INTEGER | 该领域的会话数 |
| key_patterns | TEXT (JSON) | 该领域的关键行为模式 |
| autonomy_boundary | TEXT | 自主性边界描述 |
| confidence | REAL | |
| updated_at | TEXT | |

**预计规模**：10-20 条。

### 3.3 Layer 2 → Layer 3: Episode Refs（关联表）

| 字段 | 类型 | 说明 |
|------|------|------|
| episode_id | TEXT FK | |
| target_type | TEXT | tension/principle/tradeoff/... |
| target_id | TEXT | 目标条目 id |

复合主键：(episode_id, target_type, target_id)

### 3.4 Layer 3: Policies（策略）

从 L2 各维度机械派生，纯计算。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | pol1, pol2... |
| condition | TEXT | IF 条件 |
| action | TEXT | THEN 行为 |
| exception | TEXT | UNLESS 例外 |
| rationale | TEXT | Why（来自 principle） |
| source_type | TEXT | 来源维度（principle/tension/tradeoff/...） |
| source_id | TEXT | 来源条目 id |
| domain | TEXT | 适用领域 |
| role_mode | TEXT | 适用角色 |
| confidence | REAL | 继承自来源 |
| status | TEXT | active/deprecated |
| evidence_summary | TEXT | 简要证据 |
| updated_at | TEXT | |

**预计规模**：80-200 条。

### 3.5 Layer 4: Runtime Pack

编译产物，每次 Sync 时从 L3 动态生成。

**输出目标**：
- `~/.claude/CLAUDE.md` 中 `<!-- cognitive-model:start/end -->` 区间
- `~/.claude/memory/` 下 `cognitive_*.md` 文件

**编译逻辑**：
1. SELECT policies WHERE status='active' ORDER BY confidence DESC LIMIT 25
2. 按 role_mode 分组
3. 每条 policy 格式化为 When/Do/Unless/Why
4. 写入文件

## 4. 增量更新机制

**核心原则**：写之前先查，查到类似的就合并，查不到就新增。

所有 L2 维度共用同一个写入流程：

1. Agent 提取出候选条目
2. 读取该维度同领域的现有条目
3. Agent 判断：和现有哪条在说同一件事？
4. 输出结构化操作：
   - `{"action": "update", "id": "p12", "merge_fields": {...}}`
   - `{"action": "insert", "data": {...}}`
5. Python 机械执行 SQL

**晋升机制**（适用于 tensions / principles）：
- 首次出现 → `hypothesis`
- 第二次独立出现（不同会话/项目）→ `emerging`
- 跨项目出现 + ≥3 条 episode 证据 → `confirmed`
- 长期无新证据（>90 天）→ confidence 衰减

## 5. 处理流水线

### Stage 1: Episode 提取（调 AI）

- 输入：新增/变更的 JSONL 会话
- 可并行：按项目或时间分片，派多个子 Agent
- 复用：`analyze.py` 的 corrections / queries / highlights 作为预计算信号
- 输出：INSERT INTO episodes

### Stage 2: 认知模型推断（调 AI）

- 输入：episodes 表 + 现有 Profile/Memory/Rules 数据
- 可并行：7 个维度各自独立
- 每个维度的 Agent prompt 包含：该维度现有条目（用于去重判断）+ 新 episodes
- 输出：UPDATE/INSERT 对应维度表

### Stage 3: 策略编译（纯 Python）

- 触发：L2 任何维度有变更
- 从 principles 派生 policies（IF cause THEN effect UNLESS exception）
- 从 tensions 派生冲突解决策略
- 从 tradeoffs 派生场景策略
- 从 communication contract 派生沟通规则
- 输出：REPLACE INTO policies

### Stage 4: Runtime 导出（纯 Python）

- 触发：用户点击 Sync 按钮
- 从 policies 表精选 top 25
- 编译为 CLAUDE.md 段落 + memory 文件
- 覆盖写入（marker 区间替换）

## 6. API 设计

| Method | Endpoint | 说明 |
|--------|----------|------|
| GET | `/api/twin/overview` | 7 维度摘要（每维度 top 3 + 总数 + 置信度分布） |
| GET | `/api/twin/dimension/:name` | 某维度全部条目（支持排序/过滤） |
| GET | `/api/twin/item/:type/:id` | 单条详情 + 关联 episodes |
| GET | `/api/twin/policies` | 全部策略 |
| GET | `/api/twin/trace/:policy_id` | 策略追溯：policy → principle → episodes |
| GET | `/api/twin/stats` | 整体统计 |
| POST | `/api/twin/analyze` | 触发分析流水线（SSE 流式） |
| POST | `/api/twin/sync` | 触发 Runtime Pack 导出 |

## 7. UI: Digital Twin Tab

左侧栏新增独立 tab（与 Sessions / AI Evolve / Insights 平级）。

### 7.1 概览页

- 7 个维度摘要卡片
- 每张卡片：维度图标 + 名称 + 条目数 + 置信度指示条 + top 3 条目预览
- 点击卡片 → 进入该维度详情

### 7.2 维度详情页

- 条目列表，支持按 confidence / recency / domain 排序过滤
- 每条展开后显示：完整描述 + 关联条目 + 支撑 episodes
- Episodes 可点击跳转到原始会话

### 7.3 策略页

- 全部 active policies 列表
- 每条显示：IF/THEN/UNLESS + rationale + evidence 摘要
- 点击可追溯到源 principle 和 episodes

### 7.4 分析控制

- Analyze 按钮：触发 Stage 1-3 流水线，SSE 流式显示进度
- Sync 按钮：触发 Stage 4 导出
- 上次分析时间 + 条目变更统计

## 8. 文件变更清单

| 文件 | 变更 |
|------|------|
| `db.py` | +10 张表（episodes, episode_refs, tensions, principles, tradeoffs, reasoning_styles, communication_contracts, role_modes, domain_expertise, policies）+ 查询函数 |
| `analyze.py` | +CLI 命令：`twin-episodes`, `twin-extract`, `twin-compile`, `twin-stats` |
| `server.py` | +8 API endpoints, +分析流水线编排, +Sync 逻辑 |
| `static/index.html` | +Digital Twin 侧边栏按钮, +twin-view 容器 |
| `static/twin.js` | 新文件，Digital Twin 页面全部 UI 逻辑 |
| `static/app.js` | +Twin 视图切换逻辑, +键盘快捷键 `4` |
| `static/style.css` | +Twin 页面样式 |

## 9. 不做

- 不改现有 Evolve 5 个 tab 的任何逻辑
- 不改现有 Memory/Profile 的数据结构
- 不做场景模拟器（Phase 2 后续迭代）
- 不做团队级聚合
- 不做自动触发分析（手动 Analyze 按钮）
