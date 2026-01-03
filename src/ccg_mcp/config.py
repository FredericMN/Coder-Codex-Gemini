"""配置加载模块

优先级：配置文件 > 环境变量
配置文件路径：~/.ccg-mcp/config.toml
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """配置错误"""
    pass


def get_config_path() -> Path:
    """获取配置文件路径"""
    return Path.home() / ".ccg-mcp" / "config.toml"


def load_config() -> dict[str, Any]:
    """加载配置，优先级：配置文件 > 环境变量

    Returns:
        配置字典，包含 coder 和 codex 配置

    Raises:
        ConfigError: 未找到有效配置时抛出
    """
    config_path = get_config_path()

    # 优先读取配置文件
    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"配置文件格式错误：{e}")

    # 兜底：从环境变量读取
    if os.environ.get("CODER_API_TOKEN"):
        return {
            "coder": {
                "api_token": os.environ["CODER_API_TOKEN"],
                "base_url": os.environ.get(
                    "CODER_BASE_URL",
                    "https://open.bigmodel.cn/api/anthropic"
                ),
                "model": os.environ.get("CODER_MODEL", "glm-4.7"),
            }
        }

    # 生成配置引导信息
    config_example = '''# ~/.ccg-mcp/config.toml

[coder]
api_token = "your-api-token"  # 必填
base_url = "https://open.bigmodel.cn/api/anthropic"  # 示例：GLM API
model = "glm-4.7"  # 示例：GLM-4.7，可替换为其他模型

# 可选：额外环境变量
[coder.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
'''

    raise ConfigError(
        f"未找到 Coder 配置！\n\n"
        f"Coder 工具需要用户自行配置后端模型。\n"
        f"推荐使用 GLM-4.7 作为参考案例，也可选用其他支持 Claude Code API 的模型（如 Minimax、DeepSeek 等）。\n\n"
        f"请创建配置文件：{config_path}\n\n"
        f"配置文件示例：\n{config_example}\n"
        f"或设置环境变量 CODER_API_TOKEN"
    )


def build_coder_env(config: dict[str, Any]) -> dict[str, str]:
    """构建 Coder 调用所需的环境变量

    Args:
        config: 配置字典

    Returns:
        包含所有环境变量的字典
    """
    coder_config = config.get("coder", {})
    model = coder_config.get("model", "glm-4.7")

    env = os.environ.copy()

    # API 认证
    env["ANTHROPIC_AUTH_TOKEN"] = coder_config.get("api_token", "")
    env["ANTHROPIC_BASE_URL"] = coder_config.get(
        "base_url",
        "https://open.bigmodel.cn/api/anthropic"
    )

    # 所有模型别名都映射到配置的模型
    env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model
    env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model
    env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = model
    env["CLAUDE_CODE_SUBAGENT_MODEL"] = model

    # 用户自定义的额外环境变量
    for key, value in coder_config.get("env", {}).items():
        env[key] = str(value)

    return env


def validate_config(config: dict[str, Any]) -> None:
    """验证配置有效性

    Args:
        config: 配置字典

    Raises:
        ConfigError: 配置无效时抛出
    """
    coder_config = config.get("coder", {})

    if not coder_config.get("api_token"):
        raise ConfigError("Coder 配置缺少 api_token")

    if not coder_config.get("base_url"):
        raise ConfigError("Coder 配置缺少 base_url")


# 全局配置缓存
_config_cache: dict[str, Any] | None = None


def get_config() -> dict[str, Any]:
    """获取配置（带缓存）

    首次调用时加载配置并验证，后续调用直接返回缓存

    Returns:
        配置字典
    """
    global _config_cache

    if _config_cache is None:
        _config_cache = load_config()
        validate_config(_config_cache)

    return _config_cache


def reset_config_cache() -> None:
    """重置配置缓存（主要用于测试）"""
    global _config_cache
    _config_cache = None
