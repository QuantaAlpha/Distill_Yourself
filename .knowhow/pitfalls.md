# Pitfalls

## [架构] Cognitive Model 独立于 Memory — 不要混合
现象：初始设计曾考虑将认知模型合并到现有 Memory 系统
根因：Memory 是给 AI runtime 读的精简指令，认知模型是理解层，职责不同
方案：完全独立的表/API/UI，Cognitive Model 生成 → Memory/Policies 消费
位置 db.py::cm_*  日期 06-25

## [数据] worktree 子 Agent 改动可能不在主分支
现象：用 isolation:"worktree" 派子 Agent 改代码，worktree 被自动清理但改动在分支上
根因：worktree 清理策略——有改动时保留分支但清理目录
方案：子 Agent 改动如果 worktree 已清理，需手动 cherry-pick 或重新实现
位置 analyze.py server.py  日期 06-25
