# Coder 工具详细规范

## 工具说明

Coder 是可配置的代码执行工具，需要用户自行配置后端模型。推荐使用 GLM-4.7 作为参考案例，也可选用其他支持 Claude Code API 的模型（如 Minimax、DeepSeek 等）。

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| PROMPT | string | ✅ | 任务指令 |
| cd | Path | ✅ | 工作目录 |
| sandbox | string | | 默认 `workspace-write` |
| SESSION_ID | string | | 会话 ID，复用保持上下文 |
| return_all_messages | boolean | | 调试时设为 True |
| return_metrics | boolean | | 返回值中包含指标数据，默认 False |
| timeout | int | | 空闲超时（秒），默认 300，无输出超过此时间触发 |
| max_duration | int | | 总时长硬上限（秒），默认 1800（30 分钟），0 表示无限制 |
| max_retries | int | | 最大重试次数，默认 0（不重试） |
| log_metrics | boolean | | 将指标输出到 stderr |

## 返回值

```json
// 成功
{
  "success": true,
  "tool": "coder",
  "SESSION_ID": "uuid-string",
  "result": "Coder 回复内容"
}

// 失败（结构化错误）
{
  "success": false,
  "tool": "coder",
  "error": "错误摘要信息",
  "error_kind": "idle_timeout | timeout | command_not_found | upstream_error | ...",
  "error_detail": {
    "message": "错误简述",
    "exit_code": 1,
    "last_lines": ["最后20行输出..."],
    "json_decode_errors": 2,
    "idle_timeout_s": 300,
    "max_duration_s": 1800,
    "retries": 0
  }
}
```

### error_kind 枚举

| 值 | 说明 |
|----|------|
| `idle_timeout` | 空闲超时（无输出） |
| `timeout` | 总时长超时 |
| `command_not_found` | claude CLI 未安装 |
| `upstream_error` | CLI 返回错误 |
| `json_decode` | JSON 解析失败 |
| `protocol_missing_session` | 未获取 SESSION_ID |
| `empty_result` | 无响应内容 |
| `subprocess_error` | 进程退出码非零 |
| `config_error` | 配置加载失败 |
| `unexpected_exception` | 未预期异常 |

## Prompt 模板

```
请执行以下代码任务：

**任务类型**：[新增功能 / 修复 Bug / 重构 / 其他]
**目标文件**：[文件路径]

**具体要求**：
1. [要求1]
2. [要求2]

**约束条件**：
- [约束1]
- [约束2]

**验收标准**：
- [标准1]

请严格按照上述范围修改代码，完成后说明改动内容。
```

## 使用规范

1. **必须保存** `SESSION_ID` 以便多轮对话
2. 检查 `success` 字段判断执行是否成功
3. 从 `result` 字段获取回复内容
4. 失败时检查 `error_kind` 决定是否可重试
5. 调试时设置 `return_all_messages=True` 或 `return_metrics=True`

## 重试策略

Coder 默认 **不自动重试**（有写入副作用），如需重试：
- 显式设置 `max_retries=1` 或更高
- 仅对幂等操作启用重试
- 重试采用指数退避（0.5s → 1s → 2s）
