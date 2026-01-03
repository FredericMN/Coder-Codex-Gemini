"""Gemini 工具实现

调用 Gemini CLI 进行代码执行、技术咨询或代码审核。
Gemini 是多面手，权限灵活，由 Claude 按场景控制。
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, Generator, Iterator, List, Literal, Optional

from pydantic import Field


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

def run_gemini_command(
    cmd: list[str],
    timeout: int = 300,
    max_duration: int = 1800,
    prompt: str = "",
    cwd: Optional[Path] = None,
) -> Generator[str, None, tuple[Optional[int], int]]:
    """执行 Gemini 命令并流式返回输出

    Args:
        cmd: 命令和参数列表
        timeout: 空闲超时（秒），无输出超过此时间触发超时，默认 300 秒（5 分钟）
        max_duration: 总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制
        prompt: 通过 stdin 传递的 prompt 内容
        cwd: 工作目录

    Yields:
        输出行

    Returns:
        (exit_code, raw_output_lines) 元组

    Raises:
        CommandNotFoundError: gemini CLI 未安装时抛出
        CommandTimeoutError: 命令执行超时时抛出
    """
    gemini_path = shutil.which('gemini')
    if not gemini_path:
        raise CommandNotFoundError(
            "未找到 gemini CLI。请确保已安装 Gemini CLI 并添加到 PATH。\n"
            "安装指南：https://github.com/google-gemini/gemini-cli"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = gemini_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace',  # 处理非 UTF-8 字符，避免 UnicodeDecodeError
        cwd=str(cwd) if cwd else None,
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

    def is_turn_completed(line: str) -> bool:
        """检查是否回合完成"""
        try:
            data = json.loads(line)
            # Gemini CLI 使用 turn.completed 表示回合完成
            return data.get("type") == "turn.completed"
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
                if is_turn_completed(stripped):
                    # 等待剩余输出被 drain
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
                f"gemini 执行超时（总时长超过 {max_duration}s），进程已终止。",
                is_idle=False
            )
            break

        # 检查空闲超时
        if (now - last_activity_time) >= timeout:
            timeout_error = CommandTimeoutError(
                f"gemini 空闲超时（{timeout}s 无输出），进程已终止。",
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
            f"gemini 进程等待超时，进程已终止。",
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


@contextmanager
def safe_gemini_command(
    cmd: list[str],
    timeout: int = 300,
    max_duration: int = 1800,
    prompt: str = "",
    cwd: Optional[Path] = None,
) -> Iterator[Generator[str, None, tuple[Optional[int], int]]]:
    """安全执行 Gemini 命令的上下文管理器

    确保在任何情况下（包括异常）都能正确清理子进程。

    用法:
        with safe_gemini_command(cmd, timeout, max_duration, prompt, cwd) as gen:
            for line in gen:
                process_line(line)
    """
    gemini_path = shutil.which('gemini')
    if not gemini_path:
        raise CommandNotFoundError(
            "未找到 gemini CLI。请确保已安装 Gemini CLI 并添加到 PATH。\n"
            "安装指南：https://github.com/google-gemini/gemini-cli"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = gemini_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace',  # 处理非 UTF-8 字符，避免 UnicodeDecodeError
        cwd=str(cwd) if cwd else None,
    )

    thread: Optional[threading.Thread] = None

    def cleanup() -> None:
        """清理子进程和线程（best-effort，不抛异常）"""
        nonlocal thread
        # 1. 先关闭 stdout 以解除读取线程的阻塞
        try:
            if process.stdout and not process.stdout.closed:
                process.stdout.close()
        except (OSError, IOError):
            pass
        # 2. 终止进程
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=2)  # kill 后也设超时
                    except subprocess.TimeoutExpired:
                        pass  # 极端情况：进程无法终止，放弃
        except (ProcessLookupError, OSError):
            pass  # 进程已退出，忽略
        # 3. 等待线程结束
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)

    try:
        # 通过 stdin 传递 prompt，然后关闭 stdin
        if process.stdin:
            try:
                if prompt:
                    process.stdin.write(prompt)
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

        output_queue: queue.Queue[str | None] = queue.Queue()
        raw_output_lines_holder = [0]
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
            try:
                if process.stdout:
                    for line in iter(process.stdout.readline, ""):
                        stripped = line.strip()
                        output_queue.put(stripped)
                        if stripped:
                            raw_output_lines_holder[0] += 1
                        if is_turn_completed(stripped):
                            time.sleep(GRACEFUL_SHUTDOWN_DELAY)
                            break
                    process.stdout.close()
            except (OSError, IOError, ValueError):
                pass  # stdout 被关闭，正常退出
            finally:
                output_queue.put(None)  # 确保投递哨兵

        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()

        def generator() -> Generator[str, None, tuple[Optional[int], int]]:
            """生成器：读取输出并处理超时"""
            nonlocal thread
            start_time = time.time()
            last_activity_time = time.time()
            timeout_error: CommandTimeoutError | None = None

            while True:
                now = time.time()

                if max_duration > 0 and (now - start_time) >= max_duration:
                    timeout_error = CommandTimeoutError(
                        f"gemini 执行超时（总时长超过 {max_duration}s），进程已终止。",
                        is_idle=False
                    )
                    break

                if (now - last_activity_time) >= timeout:
                    timeout_error = CommandTimeoutError(
                        f"gemini 空闲超时（{timeout}s 无输出），进程已终止。",
                        is_idle=True
                    )
                    break

                try:
                    line = output_queue.get(timeout=0.5)
                    if line is None:
                        break
                    last_activity_time = time.time()
                    if line:
                        yield line
                except queue.Empty:
                    if process.poll() is not None and not thread.is_alive():
                        break

            if timeout_error is not None:
                cleanup()
                raise timeout_error

            exit_code: Optional[int] = None
            try:
                exit_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                timeout_error = CommandTimeoutError(
                    f"gemini 进程等待超时，进程已终止。",
                    is_idle=False
                )
            finally:
                if thread is not None:
                    thread.join(timeout=5)

            if timeout_error is not None:
                raise timeout_error

            while not output_queue.empty():
                try:
                    line = output_queue.get_nowait()
                    if line is not None:
                        yield line
                except queue.Empty:
                    break

            return (exit_code, raw_output_lines_holder[0])

        yield generator()

    except Exception:
        cleanup()
        raise
    finally:
        cleanup()


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
# 可重试错误判断
# ============================================================================

def _is_retryable_error(error_kind: Optional[str], err_message: str) -> bool:
    """判断错误是否可以重试

    Gemini 默认 yolo 模式，大部分错误都可以安全重试。
    排除：命令不存在（需要用户干预）
    """
    if error_kind == ErrorKind.COMMAND_NOT_FOUND:
        return False
    # 其他错误都可以重试
    return True


# ============================================================================
# 主工具函数
# ============================================================================

async def gemini_tool(
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
        Field(description="指定模型版本"),
    ] = "",
    timeout: Annotated[
        int,
        Field(description="空闲超时（秒），无输出超过此时间触发超时，默认 300 秒"),
    ] = 300,
    max_duration: Annotated[
        int,
        Field(description="总时长硬上限（秒），默认 1800 秒（30 分钟），0 表示无限制"),
    ] = 1800,
    max_retries: Annotated[int, "最大重试次数，默认 1"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Gemini 任务

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
    """
    # 初始化指标收集器
    sandbox_str = "yolo" if yolo else sandbox
    metrics = MetricsCollector(tool="gemini", prompt=PROMPT, sandbox=sandbox_str)

    # 构建命令
    # gemini CLI 命令格式: gemini [options]
    # 使用 -y/--yolo 跳过确认，--sandbox 启用沙箱
    # 参考: https://geminicli.com/docs/cli/headless/
    cmd = ["gemini"]

    # 添加流式 JSON 输出格式（用于 headless mode）
    cmd.extend(["--output-format", "stream-json"])

    # 注意：gemini CLI 没有 --dir 参数，使用 --include-directories 或依赖 cwd
    # 工作目录通过 subprocess 的 cwd 参数设置

    # 设置沙箱模式和审批模式
    if yolo:
        # yolo 模式：自动批准所有操作
        cmd.append("--yolo")
    else:
        # 非 yolo 模式：根据 sandbox 设置
        if sandbox == "read-only":
            # read-only 需要启用 sandbox
            cmd.append("--sandbox")

    # 指定模型（默认使用 gemini-3-pro-preview）
    model_to_use = model if model else "gemini-3-pro-preview"
    cmd.extend(["--model", model_to_use])

    # 会话恢复
    if SESSION_ID:
        cmd.extend(["--resume", SESSION_ID])

    # PROMPT 通过 stdin 传递

    # 执行循环（支持重试）
    retries = 0
    last_error: Optional[Dict[str, Any]] = None
    all_last_lines: list[str] = []

    while retries <= max_retries:
        all_messages: list[Dict[str, Any]] = []
        agent_messages = ""
        had_error = False
        err_message = ""
        session_id: Optional[str] = None
        exit_code: Optional[int] = None
        raw_output_lines = 0
        json_decode_errors = 0
        error_kind: Optional[str] = None
        last_lines: list[str] = []

        try:
            with safe_gemini_command(cmd, timeout=timeout, max_duration=max_duration, prompt=PROMPT, cwd=cd) as gen:
                try:
                    for line in gen:
                        last_lines.append(line)
                        if len(last_lines) > 20:
                            last_lines.pop(0)

                        try:
                            line_dict = json.loads(line.strip())
                            all_messages.append(line_dict)

                            # stream-json 事件类型: init, message, tool_use, tool_result, error, result
                            # 参考: https://geminicli.com/docs/cli/headless/
                            event_type = line_dict.get("type", "")

                            # 提取 message 事件中的内容
                            if event_type == "message":
                                # message 事件包含 role 和 content
                                role = line_dict.get("role", "")
                                content = line_dict.get("content", "")
                                if role == "assistant" and content:
                                    agent_messages += content

                            # 提取 result 事件（最终统计）
                            if event_type == "result":
                                # result 事件包含 response 和统计信息
                                response = line_dict.get("response", "")
                                if response:
                                    # 如果 result 中有完整响应，使用它
                                    if not agent_messages:
                                        agent_messages = response

                            # 提取 session_id (Gemini 可能在 init 事件中返回)
                            if event_type == "init":
                                if line_dict.get("session_id") is not None:
                                    session_id = line_dict.get("session_id")
                                if line_dict.get("thread_id") is not None:
                                    session_id = line_dict.get("thread_id")

                            # 错误处理
                            if event_type == "error":
                                had_error = True
                                err_message += "\n\n[gemini error] " + line_dict.get("message", str(line_dict))
                                error_kind = ErrorKind.UPSTREAM_ERROR

                        except json.JSONDecodeError:
                            # JSON 解析失败，记录错误计数
                            json_decode_errors += 1
                            # 非 JSON 输出记录到日志但不作为响应内容
                            # 避免将 CLI 警告/错误文本误认为成功结果
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

            result: Dict[str, Any] = {
                "success": False,
                "tool": "gemini",
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
            success = False
            # 超时可以重试
            if retries < max_retries:
                all_last_lines = last_lines.copy()
                last_error = {
                    "error_kind": error_kind,
                    "err_message": err_message,
                    "exit_code": exit_code,
                    "json_decode_errors": json_decode_errors,
                    "raw_output_lines": raw_output_lines,
                }
                retries += 1
                time.sleep(0.5 * (2 ** (retries - 1)))
                continue
            else:
                # 已达最大重试次数
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
        success = True

        if had_error:
            success = False

        # Gemini 可能不返回 session_id，这不算失败
        # if session_id is None:
        #     success = False
        #     if not error_kind:
        #         error_kind = ErrorKind.PROTOCOL_MISSING_SESSION
        #     err_message = "未能获取 SESSION_ID。\n\n" + err_message

        if not agent_messages:
            success = False
            if not error_kind:
                error_kind = ErrorKind.EMPTY_RESULT
            err_message = "未能获取 Gemini 响应内容。可尝试设置 return_all_messages=True 获取详细信息。\n\n" + err_message

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
            # 检查是否可重试
            if _is_retryable_error(error_kind, err_message) and retries < max_retries:
                all_last_lines = last_lines.copy()
                last_error = {
                    "error_kind": error_kind,
                    "err_message": err_message,
                    "exit_code": exit_code,
                    "json_decode_errors": json_decode_errors,
                    "raw_output_lines": raw_output_lines,
                }
                retries += 1
                # 指数退避
                time.sleep(0.5 * (2 ** (retries - 1)))
            else:
                # 不可重试或已达到最大重试次数
                all_last_lines = last_lines.copy()
                last_error = {
                    "error_kind": error_kind,
                    "err_message": err_message,
                    "exit_code": exit_code,
                    "json_decode_errors": json_decode_errors,
                    "raw_output_lines": raw_output_lines,
                }
                break

    # 完成指标收集
    metrics.finish(
        success=success,
        error_kind=error_kind,
        result=agent_messages,
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
            "tool": "gemini",
            "SESSION_ID": session_id,
            "result": agent_messages,
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
            "tool": "gemini",
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
