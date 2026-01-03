# Codex 工具详细规范

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| PROMPT | string | ✅ | 审核任务描述 |
| cd | Path | ✅ | 工作目录 |
| sandbox | string | | **必须** `read-only` |
| SESSION_ID | string | | 会话 ID |
| return_all_messages | boolean | | 调试时设为 True |
| return_metrics | boolean | | 返回值中包含指标数据，默认 False |
| image | List[Path] | | 附加图片 |
| model | string | | 指定模型 |
| timeout | int | | 空闲超时（秒），默认 300，无输出超过此时间触发 |
| max_duration | int | | 总时长硬上限（秒），默认 1800（30 分钟），0 表示无限制 |
| max_retries | int | | 最大重试次数，默认 1（可安全重试） |
| log_metrics | boolean | | 将指标输出到 stderr |

## 返回值

```json
// 成功
{
  "success": true,
  "tool": "codex",
  "SESSION_ID": "uuid-string",
  "result": "Codex 审核结论"
}

// 失败（结构化错误）
{
  "success": false,
  "tool": "codex",
  "error": "错误摘要信息",
  "error_kind": "idle_timeout | timeout | command_not_found | upstream_error | ...",
  "error_detail": {
    "message": "错误简述",
    "exit_code": 1,
    "last_lines": ["最后20行输出..."],
    "json_decode_errors": 0,
    "idle_timeout_s": 300,
    "max_duration_s": 1800,
    "retries": 1
  }
}
```

### error_kind 枚举

| 值 | 说明 |
|----|------|
| `idle_timeout` | 空闲超时（无输出） |
| `timeout` | 总时长超时 |
| `command_not_found` | codex CLI 未安装 |
| `upstream_error` | CLI 返回错误 |
| `json_decode` | JSON 解析失败 |
| `protocol_missing_session` | 未获取 SESSION_ID |
| `empty_result` | 无响应内容 |
| `subprocess_error` | 进程退出码非零 |
| `unexpected_exception` | 未预期异常 |

## Prompt 模板

```
请 review 以下代码改动：

**改动文件**：[文件列表]
**改动目的**：[简要描述]

**请检查**：
1. 代码质量（可读性、可维护性）
2. 潜在 Bug 或边界情况
3. 需求完成度

**请给出明确结论**：
- ✅ 通过：代码质量良好，可以合入
- ⚠️ 建议优化：[具体建议]
- ❌ 需要修改：[具体问题]
```

## 使用规范

1. **严格边界**：必须 `sandbox="read-only"`，Codex 严禁修改代码
2. **必须保存** `SESSION_ID` 以便多轮对话
3. 检查 `success` 字段判断审核是否成功
4. 从 `result` 字段获取审核结论
5. 失败时检查 `error_kind` 了解失败原因

## 重试策略

Codex 默认允许 **1 次自动重试**（只读操作无副作用）：
- 超时、网络错误等会自动重试
- `command_not_found` 不会重试（需用户干预）
- 重试采用指数退避（0.5s → 1s → 2s）
