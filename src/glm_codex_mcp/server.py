"""GLM-CODEX-MCP 服务器主体

提供 glm、codex 和 gemini 三个 MCP 工具，实现多方协作。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from glm_codex_mcp.tools.glm import glm_tool
from glm_codex_mcp.tools.codex import codex_tool
from glm_codex_mcp.tools.gemini import gemini_tool

# 创建 MCP 服务器实例
mcp = FastMCP("GLM-CODEX-MCP Server")


@mcp.tool(
    name="glm",
    description="""
    调用 GLM-4.7 执行代码生成或修改任务。

    **角色定位**：代码执行者
    - 根据精确的 Prompt 生成或修改代码
    - 执行批量代码任务
    - 成本低，执行力强

    **使用场景**：
    - 新增功能：根据需求生成代码
    - 修复 Bug：根据问题描述修改代码
    - 重构：根据目标进行代码重构
    - 批量任务：执行大量相似的代码修改

    **注意**：GLM 需要写权限，默认 sandbox 为 workspace-write

    **Prompt 模板**：
    ```
    请执行以下代码任务：
    **任务类型**：[新增功能 / 修复 Bug / 重构 / 其他]
    **目标文件**：[文件路径]
    **具体要求**：
    1. [要求1]
    2. [要求2]
    **约束条件**：
    - [约束1]
    **验收标准**：
    - [标准1]
    ```
    """,
)
async def glm(
    PROMPT: Annotated[str, "发送给 GLM 的任务指令，需要精确、具体"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，默认允许写工作区"),
    ] = "workspace-write",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    timeout: Annotated[int, "空闲超时（秒），无输出超过此时间触发超时，默认 300 秒"] = 300,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制"] = 1800,
    max_retries: Annotated[int, "最大重试次数，默认 0（GLM 有写入副作用，默认不重试）"] = 0,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 GLM 代码任务"""
    return await glm_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        SESSION_ID=SESSION_ID,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


@mcp.tool(
    name="codex",
    description="""
    调用 Codex 进行代码审核。

    **角色定位**：代码审核者
    - 检查代码质量（可读性、可维护性、潜在 bug）
    - 评估需求完成度
    - 给出明确结论：✅ 通过 / ⚠️ 建议优化 / ❌ 需要修改

    **使用场景**：
    - GLM 完成代码后，调用 Codex 进行质量审核
    - 需要独立第三方视角时
    - 代码合入前的最终检查

    **注意**：Codex 仅审核，严禁修改代码，默认 sandbox 为 read-only

    **Prompt 模板**：
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
    """,
)
async def codex(
    PROMPT: Annotated[str, "审核任务描述"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，默认只读"),
    ] = "read-only",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    skip_git_repo_check: Annotated[
        bool,
        "允许在非 Git 仓库中运行",
    ] = True,
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    image: Annotated[
        Optional[List[Path]],
        Field(description="附加图片文件路径列表"),
    ] = None,
    model: Annotated[
        str,
        Field(description="指定模型，默认使用 Codex 自己的配置"),
    ] = "",
    yolo: Annotated[
        bool,
        Field(description="无需审批运行所有命令（跳过沙箱）"),
    ] = False,
    profile: Annotated[
        str,
        "从 ~/.codex/config.toml 加载的配置文件名称",
    ] = "",
    timeout: Annotated[int, "空闲超时（秒），无输出超过此时间触发超时，默认 300 秒"] = 300,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制"] = 1800,
    max_retries: Annotated[int, "最大重试次数，默认 1（Codex 只读可安全重试）"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Codex 代码审核"""
    return await codex_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        SESSION_ID=SESSION_ID,
        skip_git_repo_check=skip_git_repo_check,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        image=image,
        model=model,
        yolo=yolo,
        profile=profile,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


@mcp.tool(
    name="gemini",
    description="""
    调用 Gemini CLI 进行代码执行、技术咨询或代码审核。

    **角色定位**：多面手（与 Claude、Codex 同等级别的顶级 AI 专家）
    - 🧠 高阶顾问：架构设计、技术选型、复杂方案讨论
    - ⚖️ 独立审核：代码 Review、方案评审、质量把关
    - 🔨 代码执行：原型开发、功能实现（尤其擅长前端/UI）

    **使用场景**：
    - 用户明确要求使用 Gemini
    - 需要第二意见或独立视角
    - 架构设计和技术讨论
    - 前端/UI 原型开发

    **注意**：Gemini 权限灵活，默认 yolo=true，由 Claude 按场景控制
    **重试策略**：默认允许 1 次重试

    **Prompt 模板**：
    ```
    请提供专业意见/执行以下任务：
    **任务类型**：[咨询 / 审核 / 执行]
    **背景信息**：[项目上下文]
    **具体问题/任务**：
    1. [问题/任务1]
    2. [问题/任务2]
    **期望输出**：
    - [输出格式/内容要求]
    ```
    """,
)
async def gemini(
    PROMPT: Annotated[str, "任务指令，需提供充分背景信息"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，默认允许写工作区"),
    ] = "workspace-write",
    yolo: Annotated[
        bool,
        Field(description="无需审批运行所有命令（跳过沙箱），默认 true"),
    ] = True,
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    model: Annotated[
        str,
        Field(description="指定模型版本，默认使用 gemini-3-pro-preview"),
    ] = "",
    timeout: Annotated[int, "空闲超时（秒），无输出超过此时间触发超时，默认 300 秒"] = 300,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制"] = 1800,
    max_retries: Annotated[int, "最大重试次数，默认 1"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Gemini 任务"""
    return await gemini_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        yolo=yolo,
        SESSION_ID=SESSION_ID,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        model=model,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


def run() -> None:
    """启动 MCP 服务器"""
    mcp.run(transport="stdio")
