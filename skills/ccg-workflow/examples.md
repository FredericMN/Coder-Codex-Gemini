# 使用案例

## 案例 1：批量代码生成

**场景**：用户要求生成多个 API 接口

**流程**：
1. Claude 拆解需求，明确接口列表
2. 调用 Coder 批量生成代码
3. 确认结果，调用 Codex review
4. 根据 review 结果迭代

**Coder 调用示例**：
```
PROMPT: 请生成以下 REST API 接口：
- GET /users - 获取用户列表
- POST /users - 创建用户
- GET /users/{id} - 获取单个用户

cd: /project/src
SESSION_ID: ""  # 新会话
```

---

## 案例 2：Bug 修复

**场景**：用户报告登录功能异常

**流程**：
1. Claude 分析问题，定位原因
2. 调用 Coder 修复代码
3. 调用 Codex review 修复质量

**Coder 调用示例**：
```
PROMPT: 修复登录功能的 token 过期问题
目标文件：src/auth/login.py
问题：token 刷新逻辑缺失

cd: /project
SESSION_ID: "abc-123"  # 复用会话
```

---

## 案例 3：代码审核

**场景**：开发完成后请求 review

**Codex 调用示例**：
```
PROMPT: 请 review src/api/ 目录下的改动
改动目的：新增用户管理 API
请检查代码质量和潜在问题

cd: /project
sandbox: read-only
SESSION_ID: "abc-123"  # 复用上一步 Coder 的会话，保持上下文连贯
```

**注意**：若之前调用过 Coder 生成代码，建议复用同一 SESSION_ID，让 Codex 了解完整上下文。
