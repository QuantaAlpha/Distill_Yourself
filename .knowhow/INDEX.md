# 项目文档导航

## 当前状态
Phase 1 (Core Platform) ✅ → Phase 2 (Evolve AI) ✅ → **Phase 3 (Cognitive Model / Digital Twin) 🔄**

## 文档索引

| ID | 文档路径 | 类型 | 阶段 | 状态 | 日期 | 关联 | 说明 |
|----|---------|------|------|------|------|------|------|
| D01 | docs/specs/2026-06-22-evolve-sync-design.md | spec | Ph2 | done | 06-22 | — | Evolve Sync 到 CLAUDE.md/memory 的设计 |
| D02 | docs/plans/2026-06-23-sqlite-preaggregation.md | plan | Ph2 | done | 06-23 | — | SQLite 预聚合迁移计划 |
| D03 | docs/plans/2026-06-24-memory-schema-v2.md | plan | Ph2 | done | 06-24 | — | Memory v2 schema 升级计划 |
| D04 | docs/specs/2026-06-25-cognitive-model-spec.md | spec | Ph3 | active | 06-25 | →D05 | Cognitive Model 4层+7维度设计 |
| D05 | docs/plans/2026-06-25-cognitive-model-plan.md | plan | Ph3 | active | 06-25 | D04 | Cognitive Model 实施计划 |

## 开发时间线

### Phase 1 — Core Platform (done, 06-18~06-21)
- 会话浏览器 + FTS 搜索 + SQLite 存储 + Insights 5 tabs

### Phase 2 — Evolve AI (done, 06-22~06-24)
- [D01] Evolve Sync 设计 → 实现 Profile/Memory 同步到 CLAUDE.md
- [D02] SQLite 预聚合 → [D03] Memory Schema v2
- 关键决策：Memory 采用 trigger/instruction/avoid 格式

### Phase 3 — Cognitive Model / Digital Twin (active, 06-25~)
- [D04] Spec: 4 层流水线 + 7 认知维度
- [D05] Plan: DB schema → CLI → API → UI
- 关键决策：Cognitive Model 独立于 Memory，不修改现有模块
- 下一步：实现 AI 驱动的 Episode 提取和认知推断流水线
