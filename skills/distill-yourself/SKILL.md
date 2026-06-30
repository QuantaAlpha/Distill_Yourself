---
name: distill-yourself
description: "在对话中直接蒸馏你自己的 Claude Code / Codex 历史，并把洞见写回 AI 配置——不用开网页。当用户说『蒸馏一下我的偏好/记住我的习惯/更新我的 memory』『我是什么样的开发者/生成开发者画像』『建/更新我的认知模型/分析我怎么决策』『我反复纠正了什么/纠正趋势/反复踩的坑』『从我的对话历史里总结 X』时触发。本 skill 调用本地 distill CLI 读对话历史聚合数据，由当前对话的 agent 充当蒸馏大脑，预览后写回 ~/.claude/。不要用于：单次事实查询、与个人历史无关的普通任务、或用户明确只要看网页版时。"
---

# Distill Yourself —— 在对话里蒸馏你自己

你是用户认知的**蒸馏器**。把 Claude Code / Codex 的历史对话，提炼成能写回 AI 配置、让未来 session 受益的持久洞见。

**核心原则**：网页版 Evolve 是另起一个 `claude -p` 进程来蒸馏；而你**就在对话里**，你本身就是那个 LLM。所以你不外包蒸馏——你用本地 `distill` CLI 拿数据、自己想、预览、写回。

## CLI 入口

本 skill 假设 PATH 上有 `distill` 命令（= `analyze.py` 的全局入口）。
如果没有，把下文所有 `distill` 替换成 `python3 <仓库路径>/analyze.py`。
所有命令都是**本地只读**地分析 `~/.claude/` 和 `~/.codex/`，唯一的写操作是最后写回配置那一步。

## 通用工作流（所有能力共用）

```
0. INDEX   —— 先刷新索引，否则总览可能是空的
1. ORIENT  —— 跑总览命令拿"地图"（digest / aggregates / stats）
2. EXPLORE —— 顺着地图钻进原始数据（corrections / read / search …）
3. DISTILL —— 你自己蒸馏成有证据支撑的洞见
4. PREVIEW —— 把要写入的内容给用户看，等明确确认
5. WRITE   —— 确认后才写回
```

> **digest 是地图，不是终点。** 总览只用来定位，真正的洞见要钻进原始对话里看：什么触发了纠正、用户当时到底想要什么。只复述总览统计（"用户纠正了 8 次"）是不合格的。

### Step 0 — 刷新索引（每次开头必做）

```bash
distill refresh   # 扫 JSONL，重建 SQLite + 刷新聚合（等价网页 /api/refresh）
```
`aggregates` / `profile-digest` / `sessions` 只读 SQLite，不会自己重建索引。没建过索引或有新会话时，这一步保证总览不空、不过期。

### Step 1 — ORIENT：拿总览（预拼好的聚合，直接 dump）

```bash
distill profile-digest --date all --source all   # 主图：corrections/friction/queries/decisions 汇总
distill aggregates --json                         # ~2KB：top15 项目分布 + 近14天活跃度
distill stats --date all                          # 全局计数
```

### Step 2 — EXPLORE：钻进原始数据

| 命令 | 用途 |
|------|------|
| `distill corrections --limit 100` | 用户纠正/否定 AI 的地方（50+ 信号词）+ AI 当时的回应 |
| `distill queries --limit 50` | 用户的提问/请求（找"被接受"的正向信号） |
| `distill highlights --limit 20` | 按纠正/决策密度排序的高信号会话 |
| `distill read <id> -s` | 读某个会话（summary 模式，看上下文） |
| `distill search "<关键词>"` | 全文检索 |
| `distill decisions` / `distill errors` | 架构决策点 / 复发错误 |

通用过滤参数：`--source claude|codex|all`、`--date 7d|30d|90d|all`、`--project <名>`、`--limit N`、`--json`。

---

# 能力分区

四类能力共用上面的工作流，区别只在**产出什么、写到哪、要不要 AI 蒸馏**。先按用户意图路由到对应小节：

| 用户说 | 路由到 |
|--------|--------|
| 蒸馏偏好 / 记住我的习惯 / 更新 memory | **§Memory** |
| 我是什么样的开发者 / 生成画像 | **§Profile** |
| 建认知模型 / 分析我怎么决策 / runtime pack | **§认知模型 (Twin)** |
| 我反复纠正了什么 / 纠正趋势 / 反复踩的坑 | **§Rules · Signals · Patterns** |
| 不确定 / 想全做一遍 | 先问用户要哪个，再进对应小节 |

## §Memory —— 偏好蒸馏（最常用，详细模式）

**产出**：跨项目复用的偏好卡片。**写回**：`~/.claude/memory/evolve_<id>.md`，并更新 memory 索引。

1. **ORIENT/EXPLORE**：digest 看 corrections/queries → 对高信号点跑 `corrections` / `read <id> -s` 看上下文。
2. **DISTILL**：每条偏好提炼成一张卡片，必须有证据：
   - `label`：一句话偏好（"擅自扩展 scope 前先确认"）
   - `evidence`：2-4 条原始引用，带 `session_id`，区分纠正/接受信号
   - `priority`：P0/P1/P2（纠正越频繁越高）
   - 只收**跨项目通用**的偏好，项目特定的别收
3. **STAGE**：写进 SQLite 暂存（带校验，网页版同源可见）：
   ```bash
   echo '<memory JSON>' | distill evolve-write --tab memory --mode merge --source all --date all
   ```
4. **PREVIEW**：`distill evolve-sync --tab memory --preview` → 把将新建/更新的文件清单与内容给用户看。
5. **WRITE**：确认后 `distill evolve-sync --tab memory --execute`。

> **scope 必须一致。** `evolve-sync` 按 `--source/--date/--project` 五元组从 SQLite 读暂存数据，默认 `--date 7d`。若 `evolve-write` 用的是 `--date all`，`evolve-sync` 也必须显式带 `--source all --date all`，否则读不到刚暂存的数据。
>
> **写回绝不手搓文件格式。** 统一走 `evolve-sync`，它复用网页版 `sync.py` 的写入逻辑——YAML front matter（`name`/`description`/`type: feedback`/`source: evolve-sync`）、`When/Do/Avoid` 正文、`**Evidence:**`、`evolve_<id>.md` 命名、`MEMORY.md` 索引——保证与网页版**零漂移**。`evolve-sync` 薄包一层 `sync.py` 的 preview/execute，已内置在 CLI。

## §Profile —— 开发者画像（同 Memory 模式，差异点如下）

**产出**：persona 卡片 + 能力雷达。**写回**：`~/.claude/CLAUDE.md` 里的标记区段（`append` 或 `replace`，靠 marker 判断）。

- DISTILL 产出：persona（标签 + 几条画像陈述）+ 雷达（领域/评分/依据，每项要有证据）。
- STAGE：`echo '<profile JSON>' | distill evolve-write --tab profile --mode replace --source all --date all`
- PREVIEW/WRITE：`distill evolve-sync --tab profile --preview` → 确认 → `--execute`。它写进 `~/.claude/CLAUDE.md` 的 `<!-- evolve-sync:profile:start -->` … `<!-- evolve-sync:profile:end -->` 区段（有则替换、无则追加），**绝不动区段外的用户内容**。同样不手搓格式。

## §认知模型 (Twin) —— 三层蒸馏（最重，独立 3 阶段流程）

和上面单遍蒸馏不同，认知模型是**三层渐进**：L1 证据事件 → L2 判断卡片 → L3 认知特质 → 编译成 Runtime Pack。对应网页版的多阶段 AI 流程（events→cards→traits→compile；网页版还额外做 avatar 匹配，Skill 可不做）。

每次分析用一个 `run_id`（如 `run_<日期>_<序号>`），同一 run 的写入都带上它。

- **Stage 1 · 证据事件 (events)**：从对话提取"AI做了什么→用户怎么反应→学到什么"。
  先 `distill twin-events --json` 看已有的避免重复 → `corrections`/`highlights`/`read` 挖 → 用 batch 写：
  ```bash
  echo '{"run_id":"<run>","operations":[
    {"resource":"events","action":"add","data":{
      "session_id":"<真实id>","event_index":1,
      "task_type":"coding","ai_action":"…","user_reaction":"…","resolution":"…",
      "lesson":"<可复用洞见>","signal_type":"correction",
      "signal_intensity":0.85,"domain":"coding/scope"}}
  ]}' | distill twin-batch
  ```
  字段说明（占位处填实际值，别原样照抄）：`event_index` **必填**；`task_type` ∈ coding|review|design|research；`signal_type` ∈ correction|acceptance|escalation|question；`signal_intensity` 取 0.0–1.0 的**具体数值**（强纠正 0.9+、轻纠正 0.5–0.8、接受信号 0.3–0.5）。已有相似事件用 `twin-edit` 充实，别重复 `twin-add`；写前可用 `twin-candidates` 校验、`twin-search` 去重。
- **Stage 2 · 判断卡片 (cards)**：把本 run 的 events 聚合成决策倾向（带 confidence + 支撑证据）。读 `twin-cards --run-id <run>`，用 `twin-batch` 写 cards，并 `twin-link` 把 event→card 连起来。
- **Stage 3 · 认知特质 (traits)**：从 cards 归纳出泛化的工作风格特质，每条挂在多张 card 上（`twin-link` card→trait）。
- **编译 Runtime Pack**：`distill twin-compile --run-id <run>` —— 把 cards+traits 编成可读的开发者总结。
- 这套主要写进 SQLite 的认知模型表（网页版同源）；要不要再同步进 `CLAUDE.md` 由用户决定。

## §Rules · Signals · Patterns —— 只读汇报（确定性，无需蒸馏）

这三类是**命令直接算出来的**，不需要你蒸馏、**默认不写回**，跑完整理给用户看即可：

```bash
distill evolve-rules --json      # 反复纠正 → P0/P1/P2，带原始引用
distill evolve-signals --json    # 纠正随时间是增是减
distill evolve-patterns --json   # 反复出现的问题聚类 + 建议
```

用户若想把某条 rule 固化成偏好，再引导走 §Memory 流程写回。

> 注：这是 Skill/CLI 模式下的**确定性**结果；网页版刷新 rules/signals/patterns 当前会走 AI 通道，两者口径可能略有差异，别暗示完全等同。

---

# 预览与写回纪律（硬性）

- **不预览，不写回。** 任何对 `~/.claude/CLAUDE.md` / `~/.claude/memory/` 的写入，必须先把完整内容/diff 给用户看，得到明确确认才动手。
- **只碰该碰的。** 写 `CLAUDE.md` 只动 evolve 标记区段，不动用户其它内容；写 memory 只新增/更新 `evolve_*.md`。
- **可追溯。** 每条洞见都要能指回原始 `session_id`，不允许凭印象编造。
- **本地优先。** 除了你（host agent）本身的推理，本 skill 不发起任何额外网络请求；所有数据来自本地历史。

# 依赖的 CLI 能力（均已内置）

本 skill 依赖以下命令，已在仓库实现：

| 命令 | 作用 |
|------|------|
| `distill`（console script） | 全局入口（= `chatview.cli:main`），装包后任意目录可用 |
| `distill refresh [--force]` | 扫 JSONL 重建 SQLite + 聚合（等价网页 `/api/refresh`） |
| `distill evolve-sync --tab memory\|profile [--execute]` | 把暂存的 evolve 数据写回 `~/.claude/`，复用 `sync.py`，默认 preview |
| `distill install-skill [--force]` | 把本 skill 拷进 `~/.claude/skills/`（及 `~/.codex/skills/`） |

# 安装

```bash
# 1. 装包（提供 distill CLI 与 distill-yourself 网页服务）
pip install git+https://github.com/QuantaAlpha/Distill_Yourself.git

# 2. 把本 skill 装进 Claude Code（和 Codex）
distill install-skill          # 自动拷进 ~/.claude/skills/（及 Codex）
# 或手动： cp -r skills/distill-yourself ~/.claude/skills/
```

- **Claude Code**：用 `Skill` 工具触发，或在对话里说"蒸馏一下我的偏好"。
- **Codex**：没有原生 Skill 工具，等价于 agent 读本 md 后照着跑 `distill` 命令；工具名映射参考 superpowers 的 `references/codex-tools.md`。触发更多靠用户明说"用 distill skill"。
