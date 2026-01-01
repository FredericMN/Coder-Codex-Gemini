# GLM-CODEX-MCP

> Claude + GLM + Codex 三方协作 MCP 服务器

让 Claude (Opus) 作为架构师调度 GLM 执行代码任务、Codex 审核代码质量，形成自动化的三方协作闭环。

## 核心价值

| 维度 | 价值 |
|------|------|
| **成本优化** | Opus 负责思考（贵但强），GLM 负责执行（量大管饱） |
| **能力互补** | Opus 补足 GLM 创造力短板，Codex 提供独立审核视角 |
| **质量保障** | 双重审核机制（Claude 初审 + Codex 终审） |
| **全自动闭环** | 拆解 → 执行 → 审核 → 重试，无需人工干预 |

## 角色分工

```
Claude (Opus)     →  架构师 + 初审官 + 终审官 + 协调者
GLM-4.7           →  代码执行者（生成、修改、批量任务）
Codex (OpenAI)    →  独立代码审核者（质量把关）
```

## 快速开始

### 0. 前置要求

请确保您已成功安装和配置 Claude Code 与 Codex 两个编程工具：

- [Claude Code 安装指南](https://code.claude.com/docs)
- [Codex CLI 安装指南](https://developers.openai.com/codex/quickstart)

> [!IMPORTANT]
> 请确保您的 Claude Code 版本在 **v2.0.56** 以上；Codex CLI 版本在 **v0.61.0** 以上！

请确保您已成功安装 [uv](https://docs.astral.sh/uv/) 工具：

**Windows** 在 PowerShell 中运行以下命令：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Linux/macOS** 使用 curl/wget 下载并安装：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh  # 使用 curl

wget -qO- https://astral.sh/uv/install.sh | sh   # 使用 wget
```

> [!NOTE]
> 我们极力推荐 Windows 用户在 WSL 中运行本项目！

此外，您还需要：

- **GLM API Token**（从 [智谱 AI](https://open.bigmodel.cn) 获取）

### 1. 配置 GLM

**方式一：配置文件（推荐）**

```bash
# Windows
mkdir %USERPROFILE%\.glm-codex-mcp

# macOS/Linux
mkdir -p ~/.glm-codex-mcp
```

创建配置文件 `~/.glm-codex-mcp/config.toml`：

```toml
[glm]
api_token = "your-glm-api-token"
base_url = "https://open.bigmodel.cn/api/anthropic"
model = "glm-4.7"

[glm.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
```

**方式二：环境变量**

```bash
# Windows PowerShell
$env:GLM_API_TOKEN = "your-glm-api-token"
$env:GLM_BASE_URL = "https://open.bigmodel.cn/api/anthropic"
$env:GLM_MODEL = "glm-4.7"

# macOS/Linux
export GLM_API_TOKEN="your-glm-api-token"
export GLM_BASE_URL="https://open.bigmodel.cn/api/anthropic"
export GLM_MODEL="glm-4.7"
```

### 2. 安装 MCP

#### 2.1 安装 CodexMCP（Codex 工具依赖）

```bash
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp
```

#### 2.2 安装 GLM-CODEX-MCP

```bash
claude mcp add glm-codex -s user --transport stdio -- uvx --from git+https://github.com/FredericMN/GLM-CODEX-MCP.git glm-codex-mcp
```

#### 2.3 验证安装

在终端中运行：

```bash
claude mcp list
```

> [!IMPORTANT]
> 如果看到如下描述，说明安装成功！
> ```
> codex: uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp - ✓ Connected
> glm-codex: uvx --from git+https://github.com/FredericMN/GLM-CODEX-MCP.git glm-codex-mcp - ✓ Connected
> ```

### 3. 配置权限（可选）

在 `~/.claude/settings.json` 中添加自动允许，使 Claude Code 可以自动与工具交互：

```json
{
  "permissions": {
    "allow": [
      "mcp__codex__codex",
      "mcp__glm-codex__glm",
      "mcp__glm-codex__codex"
    ]
  }
}
```

## MCP 工具

### glm

调用 GLM-4.7 执行代码生成或修改任务。

**参数：**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| PROMPT | string | ✅ | - | 任务指令 |
| cd | Path | ✅ | - | 工作目录 |
| sandbox | string | - | workspace-write | 沙箱策略 |
| SESSION_ID | string | - | "" | 会话 ID |
| return_all_messages | bool | - | false | 返回完整消息 |

### codex

调用 Codex 进行代码审核。

**参数：**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| PROMPT | string | ✅ | - | 审核任务描述 |
| cd | Path | ✅ | - | 工作目录 |
| sandbox | string | - | read-only | 沙箱策略 |
| SESSION_ID | string | - | "" | 会话 ID |
| skip_git_repo_check | bool | - | true | 允许非 Git 仓库 |
| return_all_messages | bool | - | false | 返回完整消息 |
| image | List[Path] | - | [] | 附加图片 |
| model | string | - | "" | 指定模型 |
| yolo | bool | - | false | 跳过沙箱 |
| profile | string | - | "" | 配置文件名称 |

## 协作流程

```
用户需求
    │
    ▼
1. Claude 分析需求，拆解为子任务
    │
    ▼
2. Claude 为子任务生成精确 Prompt（含边界管控）
    │
    ▼
3. 调用 GLM 工具执行代码任务  ◄───────────────┐
    │                                         │
    ▼                                         │
4. GLM 返回结果 → Claude 初审                  │
    │                                         │
    ├─ 有明显问题 → Claude 直接修改             │
    │                                         │
    ▼                                         │
5. 调用 Codex 工具深度 review                  │
    │                                         │
    ├── ✅ 通过 → 完成任务                     │
    │                                         │
    ├── ⚠️ 建议优化 → Claude 分析并修改         │
    │                                         │
    └── ❌ 需要修改 → Claude 分析根因 ──────────┤
                        │                     │
                        ├─ 简单问题 → 直接修改 ┘
                        │
                        └─ 复杂问题 → 优化 Prompt 重新调用 GLM
```

## 全局推荐提示词

<details>
<summary>点击展开全局提示词配置（推荐添加到 ~/.claude/CLAUDE.md）</summary>

```markdown
## GLM-CODEX-MCP 协作指南

你现在拥有 GLM-CODEX-MCP 提供的两个协作工具：
- **glm**：代码执行者，调用 GLM-4.7 执行代码生成和修改
- **codex**：代码审核者，调用 Codex 进行质量审核

### 核心原则

- 🎯 **充分利用 GLM**：所有代码任务优先调用 GLM，降低成本
- 🔄 **持续迭代优化**：对 Codex 发现的问题，调用 GLM 修复而非手动修改
- ✅ **质量把关**：循环迭代直到 Codex 给出 ✅ 通过
- 🚫 **严禁 Codex 修改代码**：Codex 只负责 review，不能修改代码

### 标准工作流程

1. **需求分析** → 你拆解任务，设计方案
2. **调用 GLM** → 用精确 Prompt（含边界管控）让 GLM 执行
3. **你初审** → 检查输出，发现明显问题直接改
4. **调用 Codex** → 深度 review，要求明确结论
5. **迭代修复** → 根据 Codex 反馈调用 GLM 修复，返回步骤 3
6. **重复 3-5** → 直到 Codex 给出 ✅ 通过

### GLM Prompt 模板

```
请执行以下代码任务：

**任务类型**：[新增功能 / 修复 Bug / 重构 / 其他]
**目标文件**：[文件路径]

**修改范围**：
- 仅修改 [具体函数名/类名/模块名]
- 不要修改 [其他部分]

**具体要求**：
1. [要求1]
2. [要求2]

**输入输出**：
- 输入：[参数和类型]
- 输出：[返回值和类型]

**约束条件**：
- [约束1]

**禁止事项**：
- 不要修改其他文件
- 不要改动现有接口
- 不要添加未要求的功能

请**严格按照上述范围**修改代码，完成后说明改动内容。
```

### Codex Prompt 模板

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

### 关键要点

- GLM 默认有写权限（sandbox=workspace-write）
- Codex 默认只读（sandbox=read-only）
- 使用 SESSION_ID 可实现多轮对话
- 边界管控：明确范围、输入输出、禁止事项
- 持续迭代：让 GLM 修复问题直到通过
```

</details>

## 开发

```bash
# 克隆仓库
git clone https://github.com/FredericMN/GLM-CODEX-MCP.git
cd GLM-CODEX-MCP

# 安装依赖
uv sync

# 运行测试
uv run pytest

# 本地运行
uv run glm-codex-mcp
```

## 参考资源

- [CodexMCP](https://github.com/GuDaStudio/codexmcp) - 核心参考实现
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP 框架
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- [Codex CLI](https://developers.openai.com/codex/quickstart)
- [智谱 AI](https://open.bigmodel.cn) - GLM API

## License

MIT
