"""Codex 工具实现

调用 Codex 进行代码审核。
复用 CodexMCP 的核心逻辑。
"""

from __future__ import annotations

import json
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Annotated, Any, Dict, Generator, List, Literal, Optional

from pydantic import Field


class CommandNotFoundError(Exception):
    """命令不存在错误"""
    pass


def run_codex_command(cmd: list[str]) -> Generator[str, None, None]:
    """执行 Codex 命令并流式返回输出

    Args:
        cmd: 命令和参数列表

    Yields:
        输出行

    Raises:
        CommandNotFoundError: codex CLI 未安装时抛出
    """
    codex_path = shutil.which('codex')
    if not codex_path:
        raise CommandNotFoundError(
            "未找到 codex CLI。请确保已安装 Codex CLI 并添加到 PATH。\n"
            "安装指南：https://developers.openai.com/codex/quickstart"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = codex_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
    )

    output_queue: queue.Queue[str | None] = queue.Queue()
    GRACEFUL_SHUTDOWN_DELAY = 0.3

    def is_turn_completed(line: str) -> bool:
        """检查是否回合完成"""
        try:
            data = json.loads(line)
            return data.get("type") == "turn.completed"
        except (json.JSONDecodeError, AttributeError, TypeError):
            return False

    def read_output() -> None:
        """在单独线程中读取进程输出"""
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                stripped = line.strip()
                output_queue.put(stripped)
                if is_turn_completed(stripped):
                    # 等待剩余输出被 drain
                    time.sleep(GRACEFUL_SHUTDOWN_DELAY)
                    break
            process.stdout.close()
        output_queue.put(None)

    thread = threading.Thread(target=read_output)
    thread.start()

    while True:
        try:
            line = output_queue.get(timeout=0.5)
            if line is None:
                break
            yield line
        except queue.Empty:
            if process.poll() is not None and not thread.is_alive():
                break

    # 等待进程自然退出，而不是强制 terminate
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    thread.join(timeout=5)

    # 读取剩余输出
    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
            if line is not None:
                yield line
        except queue.Empty:
            break


async def codex_tool(
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
) -> Dict[str, Any]:
    """执行 Codex 代码审核

    调用 Codex 进行代码审核。

    **角色定位**：代码审核者
    - 检查代码质量（可读性、可维护性、潜在 bug）
    - 评估需求完成度
    - 给出明确结论：✅ 通过 / ⚠️ 建议优化 / ❌ 需要修改

    **注意**：Codex 仅审核，严禁修改代码，默认 sandbox 为 read-only
    """
    # 归一化可选参数
    image_list = image or []

    # 构建命令（shell=False 时不需要转义）
    cmd = ["codex", "exec", "--sandbox", sandbox, "--cd", str(cd), "--json"]

    if image_list:
        cmd.extend(["--image", ",".join(str(p) for p in image_list)])

    if model:
        cmd.extend(["--model", model])

    if profile:
        cmd.extend(["--profile", profile])

    if yolo:
        cmd.append("--yolo")

    if skip_git_repo_check:
        cmd.append("--skip-git-repo-check")

    if SESSION_ID:
        cmd.extend(["resume", str(SESSION_ID)])

    # PROMPT 作为位置参数
    # Windows 下需要将换行符转义，避免命令行截断
    import os
    if os.name == "nt":
        escaped_prompt = PROMPT.replace('\r\n', '\\n').replace('\n', '\\n')
        cmd += ['--', escaped_prompt]
    else:
        cmd += ['--', PROMPT]

    all_messages: list[Dict[str, Any]] = []
    agent_messages = ""
    had_error = False
    err_message = ""
    thread_id: Optional[str] = None

    try:
        for line in run_codex_command(cmd):
            try:
                line_dict = json.loads(line.strip())
                all_messages.append(line_dict)

                item = line_dict.get("item", {})
                item_type = item.get("type", "")

                if item_type == "agent_message":
                    agent_messages += item.get("text", "")

                if line_dict.get("thread_id") is not None:
                    thread_id = line_dict.get("thread_id")

                # 错误处理：记录错误但不立即判断成功与否
                if "fail" in line_dict.get("type", ""):
                    had_error = True
                    err_message += "\n\n[codex error] " + line_dict.get("error", {}).get("message", "")

                if "error" in line_dict.get("type", ""):
                    error_msg = line_dict.get("message", "")
                    is_reconnecting = bool(re.match(r'^Reconnecting\.\.\.\s+\d+/\d+$', error_msg))

                    if not is_reconnecting:
                        had_error = True
                        err_message += "\n\n[codex error] " + error_msg

            except json.JSONDecodeError:
                # JSON 解析失败记录但不影响成功判定
                # 因为 Codex CLI 可能输出进度信息等非 JSON 内容
                err_message += "\n\n[json decode error] " + line
                continue

            except Exception as error:
                err_message += f"\n\n[unexpected error] {error}. Line: {line!r}"
                had_error = True
                break

    except CommandNotFoundError as e:
        return {
            "success": False,
            "tool": "codex",
            "error": str(e),
        }

    # 综合判断成功与否
    success = True

    if had_error:
        success = False

    if thread_id is None:
        success = False
        err_message = "未能获取 SESSION_ID。\n\n" + err_message

    if not agent_messages:
        success = False
        err_message = "未能获取 Codex 响应内容。可尝试设置 return_all_messages=True 获取详细信息。\n\n" + err_message

    if success:
        result: Dict[str, Any] = {
            "success": True,
            "tool": "codex",
            "SESSION_ID": thread_id,
            "result": agent_messages,
        }
    else:
        result = {
            "success": False,
            "tool": "codex",
            "error": err_message,
        }

    if return_all_messages:
        result["all_messages"] = all_messages

    return result
