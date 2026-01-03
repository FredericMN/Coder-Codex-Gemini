# CCG 项目重命名任务 Prompt

> 本文档用于指导 AI 完成项目从 GLM-CODEX-MCP 到 Coder-Codex-Gemini (CCG) 的全面重命名。

---

## 一、项目背景

**原项目名称**：GLM-CODEX-MCP
**新项目名称**：Coder-Codex-Gemini (简称 CCG)
**新仓库地址**：https://github.com/FredericMN/Coder-Codex-Gemini.git

### 更名原因

原 GLM 工具实际上可以配置任何支持 Claude Code API 的模型后端（如 GLM-4.7、Minimax、DeepSeek 等），"GLM" 名称过于具体。现更名为 "Coder" 以反映其"可配置代码执行者"的通用定位。

### 命名规范

| 场景 | 旧名称 | 新名称 |
|------|--------|--------|
| GitHub 仓库 | GLM-CODEX-MCP | Coder-Codex-Gemini |
| MCP 注册名 | glm-codex | ccg |
| Python 包名 | glm-codex-mcp | ccg-mcp |
| 入口命令 | glm-codex-mcp | ccg-mcp |
| 配置目录 | ~/.glm-codex-mcp/ | ~/.ccg-mcp/ |
| 工具名 (glm) | glm | coder |
| 工具名 (codex) | codex | codex（不变） |
| 工具名 (gemini) | gemini | gemini（不变） |

### 用户需手动操作

用户需手动重命名本地配置目录（已完成，可检查。）：
```powershell
# Windows
ren "C:\Users\Administrator\.glm-codex-mcp" ".ccg-mcp"

# macOS/Linux
mv ~/.glm-codex-mcp ~/.ccg-mcp
```

---

## 二、需要修改的文件清单

### 2.1 Python 源代码

| 文件/目录 | 改动内容 |
|-----------|----------|
| `src/glm_codex_mcp/` | **整个目录重命名** → `src/ccg_mcp/` |
| `src/ccg_mcp/__init__.py` | 更新模块描述 |
| `src/ccg_mcp/cli.py` | 更新 import 路径、描述文字 |
| `src/ccg_mcp/config.py` | 配置目录 `~/.glm-codex-mcp/` → `~/.ccg-mcp/`，函数名 `build_glm_env` → `build_coder_env`，`get_config` 中的 glm 相关变量名 |
| `src/ccg_mcp/server.py` | MCP 服务器名 → `ccg`、工具注册名、import 路径、`glm_tool` → `coder_tool` |
| `src/ccg_mcp/tools/__init__.py` | 更新导出：`glm_tool` → `coder_tool` |
| `src/ccg_mcp/tools/glm.py` | **重命名文件** → `coder.py`，函数名 `glm_tool` → `coder_tool`，`GLM_SYSTEM_PROMPT` → `CODER_SYSTEM_PROMPT`，所有错误信息中的 "glm" → "coder"，docstring 更新 |
| `src/ccg_mcp/tools/codex.py` | 更新 import 路径（如有引用 glm_codex_mcp） |
| `src/ccg_mcp/tools/gemini.py` | 更新 import 路径（如有引用 glm_codex_mcp） |

### 2.2 配置文件

| 文件 | 改动内容 |
|------|----------|
| `pyproject.toml` | `name` → `ccg-mcp`，`description` 更新，`authors` 更新，`keywords` 更新，`project.urls.Homepage` → 新仓库地址，`project.scripts` → `ccg-mcp = "ccg_mcp.cli:main"`，`tool.hatch.build.targets.wheel.packages` → `["src/ccg_mcp"]`，`tool.hatch.build.targets.sdist.include` 更新 |
| `config.example.toml` | 配置节名 `[glm]` → `[coder]`，注释说明更新为"可配置任意支持 Claude Code API 的模型" |

### 2.3 Skills 文件

| 文件/目录 | 改动内容 |
|-----------|----------|
| `skills/glm-codex-workflow/` | **目录重命名** → `skills/ccg-workflow/` |
| `skills/ccg-workflow/SKILL.md` | 更新 name、description、工具引用 `mcp__glm-codex__glm` → `mcp__ccg__coder` |
| `skills/ccg-workflow/glm-guide.md` | **重命名文件** → `coder-guide.md`，更新内容：工具名、参数说明、强调可配置后端 |
| `skills/ccg-workflow/codex-guide.md` | 更新引用（如有 glm-codex 相关） |
| `skills/ccg-workflow/examples.md` | 更新示例中的工具名 `glm` → `coder`，`mcp__glm-codex__*` → `mcp__ccg__*` |
| `skills/gemini-collaboration/SKILL.md` | 更新引用（如有 glm-codex 相关） |
| `skills/gemini-collaboration/gemini-guide.md` | 更新引用（如有） |

### 2.4 文档文件

| 文件 | 改动内容 |
|------|----------|
| `README.md` | 全面更新：项目名、仓库链接、安装命令、工具名、配置路径、**新增 Coder 可配置任意模型说明** |
| `README_EN.md` | 同上（英文版） |
| `CLAUDE.md` | 更新项目定位描述、工具引用、目录结构说明 |
| `docs/README.md` | 更新描述 |
| `docs/glm-codex-mcp-plan.md` | 在文件开头标记为历史文档，或更新内容 |
| `docs/global-prompt-template.md` | 更新模板中的工具名 |
| `docs/brainstorm.md` | 可保留作为历史记录，无需修改 |

### 2.5 全局 Prompt 更新（用户 ~/.claude/CLAUDE.md）

Skills 名称更新：
- `glm-codex-workflow` → `ccg-workflow`
- 工具调用示例更新

---

## 三、README 优化要求（中英双语）

### 3.1 Coder 工具说明优化

**重要**：Coder 没有默认后端，需要用户自行配置。推荐使用 GLM-4.7 作为参考案例。

**中文版本**：

在工具详解的 `coder` 部分，需要添加说明：

```markdown
### `coder` - 代码执行者

调用可配置的后端模型执行具体的代码生成或修改任务。

> **可配置后端**：Coder 工具通过 Claude Code CLI 调用后端模型。**需要用户自行配置**，推荐使用 GLM-4.7 作为参考案例，您也可以选用其他支持 Claude Code API 的模型（如 Minimax、DeepSeek 等）。
```

**英文版本**：

```markdown
### `coder` - Code Executor

Calls a configurable backend model to execute specific code generation or modification tasks.

> **Configurable Backend**: The Coder tool calls backend models through Claude Code CLI. **User configuration is required**. We recommend GLM-4.7 as a reference example, but you can also use other models supporting the Claude Code API (e.g., Minimax, DeepSeek, etc.).
```

### 3.2 配置文件说明优化

配置路径更新为 `~/.ccg-mcp/config.toml`，配置节更新为 `[coder]`：

**中文**：
```toml
[coder]
api_token = "your-api-token"  # 必填
base_url = "https://open.bigmodel.cn/api/anthropic"  # 示例：GLM API
model = "glm-4.7"  # 示例：GLM-4.7，可替换为其他模型

[coder.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
```

**英文**：
```toml
[coder]
api_token = "your-api-token"  # Required
base_url = "https://open.bigmodel.cn/api/anthropic"  # Example: GLM API
model = "glm-4.7"  # Example: GLM-4.7, can be replaced with other models

[coder.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
```

### 3.3 安装命令更新

```bash
# 安装 MCP 服务器
claude mcp add ccg -s user --transport stdio -- uvx --refresh --from git+https://github.com/FredericMN/Coder-Codex-Gemini.git ccg-mcp

# 安装 Skills
# Windows (PowerShell)
xcopy /E /I "skills\ccg-workflow" "$env:USERPROFILE\.claude\skills\ccg-workflow"
xcopy /E /I "skills\gemini-collaboration" "$env:USERPROFILE\.claude\skills\gemini-collaboration"

# macOS/Linux
cp -r skills/ccg-workflow ~/.claude/skills/
cp -r skills/gemini-collaboration ~/.claude/skills/
```

### 3.4 权限配置更新

```json
{
  "permissions": {
    "allow": [
      "mcp__ccg__coder",
      "mcp__ccg__codex",
      "mcp__ccg__gemini"
    ]
  }
}
```

---

## 四、详细执行 Todo 列表

请按以下顺序逐一执行，每完成一项标记为 completed：

### 阶段 1：核心代码重构

1. [ ] 重命名目录 `src/glm_codex_mcp/` → `src/ccg_mcp/`
2. [ ] 重命名文件 `src/ccg_mcp/tools/glm.py` → `src/ccg_mcp/tools/coder.py`
3. [ ] 更新 `src/ccg_mcp/tools/coder.py`：
   - 函数名 `glm_tool` → `coder_tool`
   - 常量名 `GLM_SYSTEM_PROMPT` → `CODER_SYSTEM_PROMPT`
   - 错误信息中的 "glm" → "coder"
   - docstring 更新
   - MetricsCollector 中的 tool 参数
4. [ ] 更新 `src/ccg_mcp/tools/__init__.py`：导出 `coder_tool`
5. [ ] 更新 `src/ccg_mcp/config.py`：
   - 配置目录路径
   - 函数名 `build_glm_env` → `build_coder_env`
   - 配置节名 `glm` → `coder`
   - 变量名更新
6. [ ] 更新 `src/ccg_mcp/server.py`：
   - MCP 服务器名 → `ccg`
   - import 路径更新
   - 工具注册：`glm_tool` → `coder_tool`，工具名 `glm` → `coder`
7. [ ] 更新 `src/ccg_mcp/cli.py`：import 路径、描述
8. [ ] 更新 `src/ccg_mcp/__init__.py`：模块描述
9. [ ] 检查 `src/ccg_mcp/tools/codex.py`：更新 import 路径（如有）
10. [ ] 检查 `src/ccg_mcp/tools/gemini.py`：更新 import 路径（如有）

### 阶段 2：配置文件更新

11. [ ] 更新 `pyproject.toml`：
    - name → `ccg-mcp`
    - description 更新
    - authors 更新
    - keywords 更新（glm → coder）
    - project.urls.Homepage → 新仓库地址
    - project.scripts → `ccg-mcp`
    - packages 路径 → `src/ccg_mcp`
12. [ ] 更新 `config.example.toml`：
    - 配置节名 `[glm]` → `[coder]`
    - 注释说明：可配置任意支持 Claude Code API 的模型

### 阶段 3：Skills 重构

13. [ ] 重命名目录 `skills/glm-codex-workflow/` → `skills/ccg-workflow/`
14. [ ] 重命名文件 `skills/ccg-workflow/glm-guide.md` → `skills/ccg-workflow/coder-guide.md`
15. [ ] 更新 `skills/ccg-workflow/SKILL.md`：
    - name → `ccg-workflow`
    - 工具引用更新
16. [ ] 更新 `skills/ccg-workflow/coder-guide.md`：
    - 工具名、参数说明
    - 强调可配置后端
17. [ ] 更新 `skills/ccg-workflow/codex-guide.md`：更新引用
18. [ ] 更新 `skills/ccg-workflow/examples.md`：工具名、MCP 引用
19. [ ] 更新 `skills/gemini-collaboration/SKILL.md`：更新引用（如有）
20. [ ] 更新 `skills/gemini-collaboration/gemini-guide.md`：更新引用（如有）

### 阶段 4：文档更新

21. [ ] 更新 `README.md`：
    - 项目名、仓库链接
    - 安装命令
    - 工具名、配置路径
    - **新增 Coder 可配置说明**（需用户配置，推荐 GLM-4.7 作为参考）
    - 权限配置示例
22. [ ] 更新 `README_EN.md`：同上（英文版）
23. [ ] 更新 `CLAUDE.md`：
    - 项目定位描述
    - 目录结构
    - 工具引用
24. [ ] 更新 `docs/README.md`：项目描述
25. [ ] 更新 `docs/global-prompt-template.md`：工具名、Skill 名
26. [ ] 处理 `docs/glm-codex-mcp-plan.md`：在开头添加历史文档声明

### 阶段 5：Git 配置与验证

27. [ ] 更新 git remote URL：
    ```bash
    git remote set-url origin https://github.com/FredericMN/Coder-Codex-Gemini.git
    ```
28. [ ] Claude 自检：搜索残留的旧名称
    ```bash
    grep -r "glm-codex" --include="*.py" --include="*.md" --include="*.toml"
    grep -r "glm_codex" --include="*.py" --include="*.md" --include="*.toml"
    grep -r "GLM-CODEX" --include="*.py" --include="*.md" --include="*.toml"
    grep -r "glm_tool" --include="*.py"
    grep -r "build_glm_env" --include="*.py"
    grep -r "GLM_SYSTEM_PROMPT" --include="*.py"
    ```
29. [ ] Claude 自检：验证 import 路径正确性（尝试 import）

---

## 五、审核要求

### 5.1 Claude 自检

完成所有改动后，执行以下检查：

```bash
# 搜索残留的旧名称（应该无结果，除了本文件和历史文档）
grep -r "glm-codex" --include="*.py" --include="*.md" --include="*.toml" | grep -v "RENAME_TASK_PROMPT.md" | grep -v "glm-codex-mcp-plan.md"
grep -r "glm_codex" --include="*.py" --include="*.md" --include="*.toml"
grep -r "GLM-CODEX" --include="*.py" --include="*.md" --include="*.toml" | grep -v "RENAME_TASK_PROMPT.md" | grep -v "glm-codex-mcp-plan.md"
grep -r "glm_tool" --include="*.py"
grep -r "build_glm_env" --include="*.py"
grep -r "GLM_SYSTEM_PROMPT" --include="*.py"
```

---

## 六、补充说明

- 本次改动不涉及业务逻辑变更，纯粹是命名重构
- 保持所有功能的向后兼容性
- `.venv/` 和 `reference/` 目录无需修改
- `docs/brainstorm.md` 可保留作为历史记录
- 本文件 `RENAME_TASK_PROMPT.md` 在任务完成后可删除或保留作为记录

---

## 七、GitHub About 简介

**中文**：
> Claude (架构师/调度) + Coder (可配置执行者如GLM/Minimax等) + Codex (审核者) + Gemini (顾问) — 多模型协作 MCP 工作流

**英文**：
> Multi-model MCP workflow: Claude (architect/orchestrator) + Coder (configurable executor e.g. GLM/Minimax) + Codex (reviewer) + Gemini (consultant)

---

**请严格按照 Todo 列表顺序执行，确保每一步都正确完成后再进行下一步。**
