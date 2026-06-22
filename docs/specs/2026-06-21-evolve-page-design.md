# Evolve Page — 设计文档

## 概述

在 Chat Viewer 中新增 **Evolve** 页面，从历史对话中 AI 实时抽取用户画像、偏好记忆、规则建议、纠正记录和重复模式，通过 D3.js 高级可视化结构化展示，让 AI Agent 越用越智能。

副标题：从对话中学习，让 AI 越用越懂你

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据来源 | AI 从历史对话实时抽取 | 用户明确要求，不依赖现有 memory 文件 |
| 可视化方案 | D3.js CDN 引入 | 表现力最强，只需一个 script tag |
| 聊天框联动 | 摘要 + 3s 自动跳转 | 不丢信息，不撑爆聊天框 |
| Tab 数量 | 5 个独立 Tab | 用户明确要求拆细 |
| 缓存策略 | localStorage + 时间戳 | 保持零后端依赖 |
| 长内容处理 | 折叠 + 弹窗放大 | 右侧 panel 聊天消息 |

## 导航位置

左侧导航新增 Evolve（在 AI Analysis 上方）：

```
Sessions | Timeline | Analytics | Snippets | Project Health | Evolve | AI Analysis
```

## 页面结构

```
┌──────────────────────────────────────────────────────────┐
│  Evolve — 从对话中学习，让 AI 越用越懂你                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 🧬 12 Profile │ 🧠 128 Memory │ 📐 23 Rules │ ...  │  │  Overview 统计条
│  │ Last scan: 2 min ago        Source ▾ Time ▾ Proj ▾  │  │  过滤器
│  └─────────────────────────────────────────────────────┘  │
│  ┌───────┬────────┬───────┬─────────┬──────────┐         │
│  │Profile│Memory  │Rules  │Signals  │Patterns  │         │  Tab 栏
│  └───────┴────────┴───────┴─────────┴──────────┘         │
│  ┌──────────────────────────────────────────────────┐    │
│  │  上次更新：2h ago                    🔄 Refresh   │    │
│  │        D3 可视化 + 结构化卡片内容区               │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

## 5 个 Tab 设计

### 1. Profile — 用户画像

**可视化**：
- 左半：D3 雷达图，6-8 维度（谨慎度/细节度/自主性/验证要求/设计品味/沟通风格/速度/直接性）
- 右半：D3 放射状思维导图，中心=用户，分支=项目/技术栈/常见任务/偏好
- 每个节点带 confidence + evidence count，点击展开来源 session

**数据结构**：
```json
{
  "radar": {"dimensions": [{"name": "Caution", "score": 0.8, "confidence": "high"}]},
  "mindmap": {"center": "User", "branches": [{"label": "Tech", "children": ["Python", "React"]}]},
  "cards": [{"category": "Working Style", "items": ["偏好简洁", "先计划后编码"]}]
}
```

### 2. Memory — 用户偏好记忆

**可视化**：
- 主区：D3 force-directed 知识图谱
  - 节点类型着色：偏好/工作流/工具/设计/沟通
  - 节点大小=出现频次，颜色深浅=置信度
- 右侧：Memory 卡片列表（内容/首次出现/最近出现/来源 session 链接）
- 点击图谱节点高亮对应卡片

**数据结构**：
```json
{
  "nodes": [{"id": "m1", "label": "偏好简洁代码", "type": "preference", "frequency": 5, "confidence": "high", "sessions": ["sid1"]}],
  "links": [{"source": "m1", "target": "m2", "strength": 0.8}],
  "cards": [{"id": "m1", "content": "...", "firstSeen": "2026-06-01", "lastSeen": "2026-06-20"}]
}
```

### 3. Rules — 规则建议

**可视化**：
- 卡片墙布局，每卡片左侧色条标优先级（P0 红/P1 黄/P2 蓝）
- 卡片内容：规则 + Why + 正反例
- 折叠展开看原始纠正证据（用户原话 + session 链接）
- 顶部按类型分组过滤

**数据结构**：
```json
{
  "rules": [{
    "id": "r1", "priority": "P0", "category": "style",
    "rule": "不要在回复末尾总结", "why": "用户多次纠正",
    "positive": "直接给代码", "negative": "最后加一段总结",
    "evidence": [{"session": "sid1", "quote": "别再总结了"}],
    "frequency": 4
  }]
}
```

### 4. Signals — 纠正记录

**可视化**：
- 主区：D3 streamgraph/timeline，横轴时间，纵轴纠正频次，按类型分层着色
- 河流变窄 = AI 在进化、纠正减少
- 点击时间线节点 → 弹出 before/correction/after 三段对比
- 下方：纠正事件列表（用户原话/AI 问题/归类/是否已转成 Rule）

**数据结构**：
```json
{
  "timeline": [{"date": "2026-06-15", "counts": {"style": 3, "scope": 1, "accuracy": 2}}],
  "events": [{
    "id": "c1", "date": "2026-06-15", "session": "sid1",
    "type": "style", "userQuote": "不要这样写",
    "aiIssue": "过度注释", "correction": "删掉注释",
    "linkedRule": "r1"
  }]
}
```

### 5. Patterns — 重复模式

**可视化**：
- 主区：D3 bubble cluster，气泡大小=频次，颜色=类型（错误/效率/知识盲区）
- 右侧：Pattern 卡片（模式描述/频次/成本估算/建议改进）
- 下方：趋势小图（哪些问题在减少/增多）

**数据结构**：
```json
{
  "bubbles": [{"id": "p1", "label": "重复搜索 API 用法", "frequency": 8, "type": "knowledge_gap", "trend": "stable"}],
  "cards": [{
    "id": "p1", "description": "...", "frequency": 8,
    "cost": "每次多花 5 min", "suggestion": "建议记录到 CLAUDE.md",
    "sessions": ["sid1", "sid2"], "trend": "decreasing"
  }]
}
```

## AI Analysis 联动

现有 AI Analysis 预设按钮（规则生成/知识沉淀等）触发分析后：
1. 后端 Codex CLI 返回结果
2. 前端解析结果为对应 Tab 的数据结构
3. 聊天框显示摘要（如 "发现 5 条规则建议、3 条用户偏好"）+ "查看详情 →" 链接
4. 3 秒后自动跳转 Evolve 页面对应 Tab
5. 结果写入 localStorage 缓存

## Evolve 页面独立触发

- 进入 Evolve 页面时展示 localStorage 缓存的上次结果
- 顶部显示"上次更新：X 前"
- 每个 Tab 有独立 🔄 Refresh 按钮
- 右上角有"全部刷新"按钮
- 刷新时调 `/api/chat` 发送对应的分析 prompt
- 首次无缓存时显示空状态引导："点击刷新，开始分析最近的对话"

## 右侧 Panel 折叠/放大

对右侧 AI 聊天 panel 的消息增加：
- **自动折叠**：AI 回复超过 300px 高度时折叠，显示"展开全文 ↓"
- **弹窗放大**：每条消息右上角 "⤢" 按钮，点击弹出全屏 modal overlay

## 缓存方案

```javascript
localStorage key: "chatview-evolve-{tab}"
value: { updatedAt: ISO timestamp, data: {tab-specific data} }
```

每个 Tab 独立缓存，刷新时只更新对应 Tab。

## 高级细节

- **骨架屏加载**：分析中显示骨架动画
- **置信度标注**：低置信度内容虚线边框 + 浅色
- **可追溯**：每条结论可点击跳转原始 session
- **D3 微动画**：图表入场 300-500ms，克制不花哨
- **过滤器**：Source/Time/Project，复用现有 scope 过滤逻辑
- **空状态引导**：友好文案而非 "No data"

## 技术约束

- D3.js v7 通过 CDN 引入（`<script src="https://d3js.org/d3.v7.min.js"></script>`）
- 不引入其他依赖
- 前端仍为 vanilla JS，新增代码直接写在 app.js 中或拆分为 evolve.js
- 后端复用现有 `/api/chat` 接口 + analyze.py CLI
- 主题沿用现有 Light Premium（紫色 accent + 白底 + 圆角阴影）
