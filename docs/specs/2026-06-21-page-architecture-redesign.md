# Chat Viewer 页面架构重设计

**Status**: approved  
**Date**: 2026-06-21  
**Scope**: 导航 + 页面结构 + 筛选系统重构

## 目标

将 7 个一级页面合并为 4 个，筛选从侧栏移到主内容区，统一全局 scope 状态。

## 现状问题

1. 7 个一级页面无层级（Sessions/Timeline/Analytics/Snippets/Health/Evolve/AI Analysis）
2. Source/Date/Project 筛选困在侧栏，不直观
3. Welcome 页和 Sessions 混为一体
4. 3 处独立维护 scope 状态（Sessions filter bar / Evolve / AI Analysis）
5. 相关功能分散（Analytics+Health+Snippets 各自独立）

## 新架构：4 页面

### 1. Home（首页仪表盘）

吸收：Welcome 页 + Timeline 热力图

**布局**：无侧栏，全宽单栏
- 顶部：统计卡片行（Total Sessions / This Week / Projects）
- 中部左：活动热力图（复用 Timeline 的日历渲染逻辑）
- 中部右：最近会话列表（Top 10，可点击跳转 Sessions）
- 底部：AI 对话框（已实现的 `#welcome-chat`）

**数据源**：`/api/sessions`（统计）+ `/api/timeline`（热力图）  
**无筛选**：展示全局概览

### 2. Sessions（会话浏览器）

吸收：原 Sessions 页

**布局**：侧栏（会话列表）+ 主区域
- **主区域顶部**：内联筛选栏（Source tabs | Date range | Project dropdown | Search）
  - 筛选栏从侧栏 `#filter-bar` 移到 `#content` 内
  - 筛选变更 → 更新侧栏列表 + 统计数字
- **侧栏**：纯会话列表（标题+日期，无筛选控件）
- **会话详情**：点击后右侧展开对话内容（与当前相同）
- **右面板**：保留 Outline + Session AI（与当前相同）

**数据源**：`/api/sessions` + `/api/session/<id>`  
**筛选**：使用全局 scope 状态

### 3. Insights（数据洞察）

吸收：Analytics + Project Health + Snippets

**布局**：无侧栏，全宽 + Tab 栏
- **顶部**：Tab 切换（File Hotspots / Tool Heatmap / Error Patterns / Project Health / Snippets）
- **每个 Tab**：复用现有渲染函数，只是容器从独立页面改为 Tab 面板

**数据源**：`/api/analytics` + `/api/project-health` + `/api/snippets`  
**无筛选**：这些 API 都是全量聚合，不支持 scope 过滤

### 4. AI（AI 分析工作台）

吸收：Evolve + AI Analysis

**布局**：左右分栏
- **左侧**：Evolve 可视化区（Tab: Profile/Memory/Rules/Signals/Patterns）
- **右侧**：AI Analysis 对话面板（preset 卡片 + 消息 + 输入框）
- **顶部共享**：内联 scope 筛选栏（Source / Date / Project）
- **侧栏**：聊天历史列表（复用现有 `panel-chat`）

**数据源**：`POST /api/chat` + `/api/evolve/*`  
**筛选**：使用全局 scope 状态（Evolve 和 AI Analysis 共享同一 scope）

## 导航系统

### 顶部水平导航

从侧栏垂直导航改为顶部水平 Tab：

```
[Logo: Chat Viewer] [Home] [Sessions] [Insights] [AI]    [🔍 Search]
```

- 4 个 Tab 足够放在顶栏
- 释放侧栏空间给内容列表
- Logo 点击 → Home
- 搜索入口在顶栏右侧（快捷键 `/` 不变）

### 侧栏行为（按页面）

| 页面 | 侧栏内容 | 是否可折叠 |
|------|---------|-----------|
| Home | 无侧栏 | — |
| Sessions | 会话列表 | 是 |
| Insights | 无侧栏 | — |
| AI | 聊天历史列表 | 是 |

### 全局 Scope 状态

统一为一组变量，所有页面共享：

```js
let globalScope = { source: "all", date: "7d", project: "" };
```

- Sessions 页顶部筛选栏修改 → 更新 `globalScope` → 同步到 AI 页
- AI 页顶部筛选栏修改 → 更新 `globalScope` → 同步到 Sessions 页
- Home 和 Insights 不受 scope 影响

## 页面合并对照表

| 旧页面 | → 新位置 | 变化说明 |
|--------|---------|---------|
| Welcome | Home | 统计卡片+AI 聊天框替代空白欢迎页 |
| Sessions | Sessions | 筛选从侧栏移到主区域，其余不变 |
| Timeline | Home（热力图组件） | 不再独立页面，日历嵌入 Home |
| Analytics | Insights Tab 1-3 | 3 个 section 变成 3 个 Tab |
| Project Health | Insights Tab 4 | 变成 Tab |
| Snippets | Insights Tab 5 | 变成 Tab |
| Evolve | AI（左侧） | 可视化区保留，scope 共享 |
| AI Analysis | AI（右侧） | 对话面板保留，scope 共享 |

## 删除项

- `#sidebar-nav`（垂直导航按钮）→ 替换为 `#top-nav`（水平 Tab）
- `#filter-bar`（侧栏筛选）→ 替换为各页面内联筛选
- `.nav-section-label`（本次新加的分组标签）→ 不再需要
- `#timeline-view`（独立页面）→ 热力图组件嵌入 Home
- `#analytics-view`、`#snippets-view`、`#health-view`（独立页面）→ 合并为 Insights Tab
- `#chat-view`（独立 AI 页面）→ 合并进 AI 页右侧

## 保留项

- 会话详情（`#conversation-view` + 右面板）：不变
- 搜索（`#search-results`）：不变，只是入口移到顶栏
- 所有 API endpoints：不变
- 所有渲染函数：复用，只改容器
- localStorage 缓存机制：不变

## 实现约束

- 零外部依赖（继续 vanilla JS + Python stdlib）
- 分步实施：先导航+Home，再 Sessions 筛选，再 Insights 合并，最后 AI 合并
- 每步可独立验证，不需要一次性全改
