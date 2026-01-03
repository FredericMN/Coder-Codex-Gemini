# Gemini 工具详细规范

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| PROMPT | string | ✅ | 任务指令，需提供充分背景 |
| cd | Path | ✅ | 工作目录 |
| sandbox | string | | 默认 `workspace-write`，灵活控制 |
| yolo | boolean | | 默认 `true`，跳过审批 |
| SESSION_ID | string | | 会话 ID，复用保持上下文 |
| model | string | | 默认 `gemini-3-pro-preview` |
| return_all_messages | boolean | | 调试时设为 True |
| return_metrics | boolean | | 返回值中包含指标数据 |
| timeout | int | | 空闲超时（秒），默认 300 |
| max_duration | int | | 总时长硬上限（秒），默认 1800 |
| max_retries | int | | 最大重试次数，默认 1 |
| log_metrics | boolean | | 将指标输出到 stderr |

## 返回值

```json
// 成功
{
  "success": true,
  "tool": "gemini",
  "SESSION_ID": "uuid-string",
  "result": "Gemini 回复内容",
  "duration": "1m30s"
}

// 失败（结构化错误）
{
  "success": false,
  "tool": "gemini",
  "error": "错误摘要信息",
  "error_kind": "idle_timeout | timeout | command_not_found | upstream_error | ...",
  "error_detail": {
    "message": "错误简述",
    "exit_code": 1,
    "last_lines": ["最后20行输出..."],
    "idle_timeout_s": 300,
    "max_duration_s": 1800,
    "retries": 1
  },
  "duration": "0m30s"
}
```

### error_kind 枚举

| 值 | 说明 |
|----|------|
| `idle_timeout` | 空闲超时（无输出） |
| `timeout` | 总时长超时 |
| `command_not_found` | gemini CLI 未安装 |
| `upstream_error` | CLI 返回错误 |
| `empty_result` | 无响应内容 |
| `subprocess_error` | 进程退出码非零 |
| `unexpected_exception` | 未预期异常 |

## Prompt 模板

```
请提供专业意见/执行任务：

**任务类型**：[咨询 / 审核 / 执行]
**背景信息**：[项目上下文]

**具体问题/任务**：
1. [问题/任务1]
2. [问题/任务2]

**期望输出**：
- [输出格式/内容要求]
```

## 使用规范

1. **必须保存** `SESSION_ID` 以便多轮对话
2. 检查 `success` 字段判断执行是否成功
3. 从 `result` 字段获取回复内容
4. 失败时检查 `error_kind` 决定是否可重试
5. **提供充分背景**：Gemini 需要完整上下文才能给出高质量回复
6. **灵活控制权限**：咨询用 `read-only`，执行用 `workspace-write`

## 重试策略

Gemini 默认允许 **1 次自动重试**：
- 超时、网络错误等会自动重试
- `command_not_found` 不会重试（需用户干预）
- 重试采用指数退避（0.5s → 1s → 2s）
