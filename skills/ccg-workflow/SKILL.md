---
name: ccg-workflow
description: |
  CCG (Coder-Codex-Gemini) collaboration for code and document tasks.
  Use when: writing/modifying code, editing documents, implementing features, fixing bugs, refactoring, or code review.
  协调 Coder 执行代码/文档改动，Codex 审核代码质量。
---

# CCG 协作流程

## 角色分工

- **Claude**：架构师 + 验收者 + 最终决策者
- **Coder**：执行者（代码/文档改动）
- **Codex**：审核者 + 高级代码顾问
- **Gemini**：高阶顾问（按需）

## 核心流程

### 1. 执行：Coder 处理所有改动

所有代码、文档等内容改动任务，**直接委托 Coder 执行**。

调用前（复杂任务推荐）：
- 搜索受影响的文件/符号
- 在 PROMPT 中列出修改清单
- **复杂问题可先与 Codex 沟通**：架构设计或复杂方案可先咨询后再委托 Coder 执行

### 2. 验收：Claude 快速检查

Coder 执行完毕后，Claude 快速读取验收：
- **无误** → 继续下一任务
- **有误** → Claude 自行修复

### 3. 审核：Codex 阶段性 Review

阶段性开发完成后，调用 Codex review：
- 检查代码质量、潜在 Bug
- 结论：✅ 通过 / ⚠️ 优化 / ❌ 修改

## 工具参考

| 工具 | 用途 | sandbox | 重试 |
|------|------|---------|------|
| Coder | 执行改动 | workspace-write | 默认不重试 |
| Codex | 代码审核 | read-only | 默认 1 次 |
| Gemini | 顾问/执行 | workspace-write (yolo) | 默认 1 次 |

**会话复用**：保存 `SESSION_ID` 保持上下文。

## 独立决策

Coder/Codex/Gemini 的意见仅供参考。你（Claude）是最终决策者，需批判性思考，做出最优决策。

详细参数：[coder-guide.md](coder-guide.md) | [codex-guide.md](codex-guide.md)
