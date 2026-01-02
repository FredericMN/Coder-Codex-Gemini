"""GLM 工具实现

调用 GLM-4.7 执行代码生成或修改任务。
通过设置环境变量让 claude CLI 使用 GLM 后端。
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, Generator, Literal, Optional

from pydantic import Field

from glm_codex_mcp.config import build_glm_env, get_config


# ============================================================================
# 错误类型定义
# ============================================================================

class CommandNotFoundError(Exception):
    """命令不存在错误"""
    pass


class CommandTimeoutError(Exception):
    """命令执行超时错误"""
    def __init__(self, message: str, is_idle: bool = False):
        super().__init__(message)
        self.is_idle = is_idle  # 标记是否为空闲超时


# ============================================================================
# 错误类型枚举
# ============================================================================

class ErrorKind:
    """结构化错误类型枚举"""
    TIMEOUT = "timeout"  # 总时长超时
    IDLE_TIMEOUT = "idle_timeout"  # 空闲超时（无输出）
    COMMAND_NOT_FOUND = "command_not_found"
    UPSTREAM_ERROR = "upstream_error"
    JSON_DECODE = "json_decode"
    PROTOCOL_MISSING_SESSION = "protocol_missing_session"
    EMPTY_RESULT = "empty_result"
    SUBPROCESS_ERROR = "subprocess_error"
    CONFIG_ERROR = "config_error"
    UNEXPECTED_EXCEPTION = "unexpected_exception"


# ============================================================================
# 指标收集
# ============================================================================

class MetricsCollector:
    """指标收集器"""

    def __init__(self, tool: str, prompt: str, sandbox: str):
        self.tool = tool
        self.sandbox = sandbox
        self.prompt_chars = len(prompt)
        self.prompt_lines = prompt.count('\n') + 1
        self.ts_start = datetime.now(timezone.utc)
        self.ts_end: Optional[datetime] = None
        self.duration_ms: int = 0
        self.success: bool = False
        self.error_kind: Optional[str] = None
        self.retries: int = 0
        self.exit_code: Optional[int] = None
        self.result_chars: int = 0
        self.result_lines: int = 0
        self.raw_output_lines: int = 0
        self.json_decode_errors: int = 0

    def finish(
        self,
        success: bool,
        error_kind: Optional[str] = None,
        result: str = "",
        exit_code: Optional[int] = None,
        raw_output_lines: int = 0,
        json_decode_errors: int = 0,
        retries: int = 0,
    ) -> None:
        """完成指标收集"""
        self.ts_end = datetime.now(timezone.utc)
        self.duration_ms = int((self.ts_end - self.ts_start).total_seconds() * 1000)
        self.success = success
        self.error_kind = error_kind
        self.result_chars = len(result)
        self.result_lines = result.count('\n') + 1 if result else 0
        self.exit_code = exit_code
        self.raw_output_lines = raw_output_lines
        self.json_decode_errors = json_decode_errors
        self.retries = retries

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "ts_start": self.ts_start.isoformat() if self.ts_start else None,
            "ts_end": self.ts_end.isoformat() if self.ts_end else None,
            "duration_ms": self.duration_ms,
            "tool": self.tool,
            "sandbox": self.sandbox,
            "success": self.success,
            "error_kind": self.error_kind,
            "retries": self.retries,
            "exit_code": self.exit_code,
            "prompt_chars": self.prompt_chars,
            "prompt_lines": self.prompt_lines,
            "result_chars": self.result_chars,
            "result_lines": self.result_lines,
            "raw_output_lines": self.raw_output_lines,
            "json_decode_errors": self.json_decode_errors,
        }

    def format_duration(self) -> str:
        """格式化耗时为 "xmxs" 格式"""
        total_seconds = self.duration_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m{seconds}s"

    def log_to_stderr(self) -> None:
        """将指标输出到 stderr（JSONL 格式）"""
        metrics = self.to_dict()
        # 移除 None 值以减少输出
        metrics = {k: v for k, v in metrics.items() if v is not None}
        try:
            print(json.dumps(metrics, ensure_ascii=False), file=sys.stderr)
        except Exception:
            pass  # 静默失败，不影响主流程


# ============================================================================
# 命令执行
# ============================================================================

def run_glm_command(
    cmd: list[str],
    env: dict[str, str],
    cwd: Path | None = None,
    timeout: int = 300,
    max_duration: int = 1800,
    prompt: str = "",
) -> Generator[str, None, tuple[Optional[int], int]]:
    """执行 GLM 命令并流式返回输出

    Args:
        cmd: 命令和参数列表
        env: 环境变量字典
        cwd: 工作目录
        timeout: 空闲超时（秒），无输出超过此时间触发超时，默认 300 秒（5 分钟）
        max_duration: 总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制
        prompt: 通过 stdin 传递的 prompt 内容

    Yields:
        输出行

    Returns:
        (exit_code, raw_output_lines) 元组

    Raises:
        CommandNotFoundError: claude CLI 未安装时抛出
        CommandTimeoutError: 命令执行超时时抛出
    """
    # 查找 claude CLI 路径
    claude_path = shutil.which('claude')
    if not claude_path:
        raise CommandNotFoundError(
            "未找到 claude CLI。请确保已安装 Claude Code CLI 并添加到 PATH。\n"
            "安装指南：https://docs.anthropic.com/en/docs/claude-code"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = claude_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        env=env,
        cwd=cwd,
    )

    # 通过 stdin 传递 prompt，然后关闭 stdin
    if process.stdin:
        try:
            if prompt:
                process.stdin.write(prompt)
        except (BrokenPipeError, OSError):
            # 子进程可能已退出，忽略写入错误
            pass
        finally:
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

    output_queue: queue.Queue[str | None] = queue.Queue()
    raw_output_lines = 0
    GRACEFUL_SHUTDOWN_DELAY = 0.3

    def is_session_completed(line: str) -> bool:
        """检查是否会话完成"""
        try:
            data = json.loads(line)
            # json 格式返回单个 result 对象
            return data.get("type") in ("result", "error")
        except (json.JSONDecodeError, AttributeError, TypeError):
            return False

    def read_output() -> None:
        """在单独线程中读取进程输出"""
        nonlocal raw_output_lines
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                stripped = line.strip()
                # 任意行都入队（触发活动判定），但只计数非空行
                output_queue.put(stripped)
                if stripped:
                    raw_output_lines += 1
                if is_session_completed(stripped):
                    time.sleep(GRACEFUL_SHUTDOWN_DELAY)
                    break
            process.stdout.close()
        output_queue.put(None)

    thread = threading.Thread(target=read_output)
    thread.start()

    # 持续读取输出，带双重超时保障
    start_time = time.time()
    last_activity_time = time.time()
    timeout_error: CommandTimeoutError | None = None

    while True:
        now = time.time()

        # 检查总时长硬上限（优先级高）
        if max_duration > 0 and (now - start_time) >= max_duration:
            timeout_error = CommandTimeoutError(
                f"glm 执行超时（总时长超过 {max_duration}s），进程已终止。",
                is_idle=False
            )
            break

        # 检查空闲超时
        if (now - last_activity_time) >= timeout:
            timeout_error = CommandTimeoutError(
                f"glm 空闲超时（{timeout}s 无输出），进程已终止。",
                is_idle=True
            )
            break

        try:
            line = output_queue.get(timeout=0.5)
            if line is None:
                break
            # 有输出（包括空行），重置空闲计时器
            last_activity_time = time.time()
            if line:  # 非空行才 yield
                yield line
        except queue.Empty:
            if process.poll() is not None and not thread.is_alive():
                break

    # 如果超时，终止进程
    if timeout_error is not None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        thread.join(timeout=5)
        raise timeout_error

    exit_code: Optional[int] = None
    try:
        exit_code = process.wait(timeout=5)  # 此时进程应已结束，短超时即可
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        # 进程等待超时（罕见情况），视为总时长超时
        timeout_error = CommandTimeoutError(
            f"glm 进程等待超时，进程已终止。",
            is_idle=False
        )
    finally:
        thread.join(timeout=5)

    if timeout_error is not None:
        raise timeout_error

    # 读取剩余输出（不再累加 raw_output_lines，避免重复计数）
    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
            if line is not None:
                yield line
        except queue.Empty:
            break

    # 返回退出码和原始输出行数
    return (exit_code, raw_output_lines)


def _build_error_detail(
    message: str,
    exit_code: Optional[int] = None,
    last_lines: Optional[list[str]] = None,
    json_decode_errors: int = 0,
    idle_timeout_s: Optional[int] = None,
    max_duration_s: Optional[int] = None,
    retries: int = 0,
) -> Dict[str, Any]:
    """构建结构化错误详情"""
    detail: Dict[str, Any] = {"message": message}
    if exit_code is not None:
        detail["exit_code"] = exit_code
    if last_lines:
        detail["last_lines"] = last_lines[-20:]  # 最多保留 20 行
    if json_decode_errors > 0:
        detail["json_decode_errors"] = json_decode_errors
    if idle_timeout_s is not None:
        detail["idle_timeout_s"] = idle_timeout_s
    if max_duration_s is not None:
        detail["max_duration_s"] = max_duration_s
    if retries > 0:
        detail["retries"] = retries
    return detail


# ============================================================================
# GLM System Prompt
# ============================================================================

GLM_SYSTEM_PROMPT = """你是一个专注高效的代码执行助手。

【SOLO 模式】当前处于 SOLO 模式，由你独立完成任务。

【执行原则】
- 直接执行任务，不闲聊、不反问需求
- 遵循代码最佳实践，保持代码质量
- 在任务范围内可自主决策实现细节

【输出规范】
- 仅输出任务结果与必要的改动说明
- 如有代码改动可附 diff（内容较多时节选关键部分并说明）"""


# ============================================================================
# 主工具函数
# ============================================================================

async def glm_tool(
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
    max_retries: Annotated[int, "最大重试次数，默认 0（不重试）"] = 0,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 GLM 代码任务

    调用 GLM-4.7 执行代码生成或修改任务。

    **角色定位**：代码执行者
    - 根据精确的 Prompt 生成或修改代码
    - 执行批量代码任务
    - 成本低，执行力强

    **注意**：GLM 需要写权限，默认 sandbox 为 workspace-write
    **重试策略**：GLM 默认不重试（有写入副作用），除非显式设置 max_retries
    """
    # 初始化指标收集器
    metrics = MetricsCollector(tool="glm", prompt=PROMPT, sandbox=sandbox)

    # 获取配置并构建环境变量
    try:
        config = get_config()
        env = build_glm_env(config)
    except Exception as e:
        error_msg = f"配置加载失败：{e}"
        metrics.finish(success=False, error_kind=ErrorKind.CONFIG_ERROR)
        if log_metrics:
            metrics.log_to_stderr()

        result: Dict[str, Any] = {
            "success": False,
            "tool": "glm",
            "error": error_msg,
            "error_kind": ErrorKind.CONFIG_ERROR,
            "error_detail": _build_error_detail(error_msg),
        }
        if return_metrics:
            result["metrics"] = metrics.to_dict()
        return result

    # 构建命令
    cmd = [
        "claude",
        "-p",  # print mode 标志
        "--output-format", "json",
        # 注意：不使用 --setting-sources，让 CLI 正常加载所有设置
        # 递归风险通过 system-prompt 中的角色限定来防止
        "--system-prompt", GLM_SYSTEM_PROMPT,
    ]

    # 添加权限参数
    if sandbox != "read-only":
        cmd.append("--dangerously-skip-permissions")

    # 会话恢复
    if SESSION_ID:
        cmd.extend(["-r", SESSION_ID])

    # PROMPT 通过 stdin 传递，不再作为命令行参数

    # 执行循环（支持重试）
    retries = 0
    last_error: Optional[Dict[str, Any]] = None
    all_last_lines: list[str] = []

    while retries <= max_retries:
        all_messages: list[Dict[str, Any]] = []
        result_content = ""
        success = True
        had_error = False
        err_message = ""
        session_id: Optional[str] = None
        exit_code: Optional[int] = None
        raw_output_lines = 0
        json_decode_errors = 0
        error_kind: Optional[str] = None
        last_lines: list[str] = []

        try:
            gen = run_glm_command(cmd, env, cd, timeout, max_duration, prompt=PROMPT)
            try:
                while True:
                    line = next(gen)
                    last_lines.append(line)
                    if len(last_lines) > 20:
                        last_lines.pop(0)

                    try:
                        line_dict = json.loads(line.strip())
                        all_messages.append(line_dict)

                        msg_type = line_dict.get("type", "")

                        if msg_type == "result":
                            result_content = line_dict.get("result", "")
                            session_id = line_dict.get("session_id")
                            if line_dict.get("is_error"):
                                had_error = True
                                err_message = result_content
                                error_kind = ErrorKind.UPSTREAM_ERROR

                        elif msg_type == "error":
                            had_error = True
                            error_data = line_dict.get("error", {})
                            err_message = error_data.get("message", str(line_dict))
                            error_kind = ErrorKind.UPSTREAM_ERROR

                    except json.JSONDecodeError:
                        json_decode_errors += 1
                        continue

                    except Exception as error:
                        err_message += f"\n\n[unexpected error] {error}. Line: {line!r}"
                        had_error = True
                        error_kind = ErrorKind.UNEXPECTED_EXCEPTION
                        break
            except StopIteration as e:
                # 正确捕获生成器返回值
                if isinstance(e.value, tuple) and len(e.value) == 2:
                    exit_code, raw_output_lines = e.value

        except CommandNotFoundError as e:
            metrics.finish(
                success=False,
                error_kind=ErrorKind.COMMAND_NOT_FOUND,
                retries=retries,
            )
            if log_metrics:
                metrics.log_to_stderr()

            result = {
                "success": False,
                "tool": "glm",
                "error": str(e),
                "error_kind": ErrorKind.COMMAND_NOT_FOUND,
                "error_detail": _build_error_detail(str(e)),
            }
            if return_metrics:
                result["metrics"] = metrics.to_dict()
            return result

        except CommandTimeoutError as e:
            # 根据异常属性区分空闲超时和总时长超时
            error_kind = ErrorKind.IDLE_TIMEOUT if e.is_idle else ErrorKind.TIMEOUT
            had_error = True
            err_message = str(e)
            success = False  # 明确设置为失败
            # 超时不重试（已经耗时太久），保存错误信息后跳出
            all_last_lines = last_lines.copy()
            last_error = {
                "error_kind": error_kind,
                "err_message": err_message,
                "exit_code": exit_code,
                "json_decode_errors": json_decode_errors,
                "raw_output_lines": raw_output_lines,
            }
            break

        # 综合判断成功与否
        if had_error:
            success = False

        if session_id is None:
            success = False
            if not error_kind:
                error_kind = ErrorKind.PROTOCOL_MISSING_SESSION
            err_message = "未能获取 SESSION_ID。\n\n" + err_message

        if not result_content and success:
            success = False
            if not error_kind:
                error_kind = ErrorKind.EMPTY_RESULT
            err_message = "未能获取 GLM 响应内容。\n\n" + err_message

        # 检查退出码
        if exit_code is not None and exit_code != 0 and success:
            success = False
            if not error_kind:
                error_kind = ErrorKind.SUBPROCESS_ERROR
            err_message = f"进程退出码非零：{exit_code}\n\n" + err_message

        if success:
            # 成功，跳出重试循环
            break
        else:
            # 失败，保存错误信息
            all_last_lines = last_lines.copy()
            last_error = {
                "error_kind": error_kind,
                "err_message": err_message,
                "exit_code": exit_code,
                "json_decode_errors": json_decode_errors,
                "raw_output_lines": raw_output_lines,
            }
            # 检查是否需要重试
            if retries < max_retries:
                retries += 1
                # 指数退避
                time.sleep(0.5 * (2 ** (retries - 1)))
            else:
                break

    # 完成指标收集
    metrics.finish(
        success=success,
        error_kind=error_kind,
        result=result_content,
        exit_code=exit_code,
        raw_output_lines=raw_output_lines,
        json_decode_errors=json_decode_errors,
        retries=retries,
    )
    if log_metrics:
        metrics.log_to_stderr()

    # 构建返回结果
    if success:
        result = {
            "success": True,
            "tool": "glm",
            "SESSION_ID": session_id,
            "result": result_content,
            "duration": metrics.format_duration(),
        }
    else:
        # 使用最后一次失败的错误信息
        if last_error:
            error_kind = last_error["error_kind"]
            err_message = last_error["err_message"]
            exit_code = last_error["exit_code"]
            json_decode_errors = last_error["json_decode_errors"]

        result = {
            "success": False,
            "tool": "glm",
            "error": err_message,
            "error_kind": error_kind,
            "error_detail": _build_error_detail(
                message=err_message.split('\n')[0] if err_message else "未知错误",
                exit_code=exit_code,
                last_lines=all_last_lines,
                json_decode_errors=json_decode_errors,
                idle_timeout_s=timeout if error_kind == ErrorKind.IDLE_TIMEOUT else None,
                max_duration_s=max_duration if error_kind == ErrorKind.TIMEOUT else None,
                retries=retries,
            ),
            "duration": metrics.format_duration(),
        }

    if return_all_messages:
        result["all_messages"] = all_messages

    if return_metrics:
        result["metrics"] = metrics.to_dict()

    return result
