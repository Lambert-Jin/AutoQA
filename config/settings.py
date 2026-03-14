"""全局配置数据类"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


def _resolve_env_vars(value: str) -> str:
    """将 ${VAR} 替换为对应环境变量的值"""
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            raise ValueError(f"Environment variable '{var_name}' is not set")
        return env_val

    return re.sub(r"\$\{(\w+)\}", _replace, value)


@dataclass
class VLMConfig:
    """VLM 配置，支持多 provider"""
    provider: str = "gemini"        # "qwen" | "gemini"
    base_url: str = ""              # Qwen 需要，Gemini 不需要
    api_key: str = "${GEMINI_API_KEY}"
    model: str = "gemini-3-pro"
    temperature: float = 0.1        # 断言场景用低温度
    max_tokens: int = 1000

    def __post_init__(self):
        if self.api_key:
            self.api_key = _resolve_env_vars(self.api_key)
        if self.base_url:
            self.base_url = _resolve_env_vars(self.base_url)


@dataclass
class AutoGLMConfig:
    """AutoGLM 模型配置"""
    base_url: str = "${AUTOGLM_BASE_URL}"
    api_key: str = "${AUTOGLM_API_KEY}"
    model: str = "autoglm-phone"
    max_tokens: int = 3000
    temperature: float = 0.1
    lang: str = "cn"                # "cn" | "en"

    def __post_init__(self):
        if self.api_key:
            self.api_key = _resolve_env_vars(self.api_key)
        if self.base_url:
            self.base_url = _resolve_env_vars(self.base_url)


@dataclass
class DeviceConfig:
    """设备配置"""
    device_type: str = "adb"        # "adb" | "hdc" | "ios"
    device_id: str | None = None    # None 为自动检测


@dataclass
class Screenshot:
    """一次截图的数据"""
    base64: str                     # 图片 base64 编码
    width: int = 0
    height: int = 0
    timestamp: float = 0.0         # time.time()
    id: str = ""                    # 唯一标识，用于报告关联

    def __post_init__(self):
        import time
        import uuid
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.id:
            self.id = uuid.uuid4().hex[:8]


@dataclass
class AssertResult:
    """断言结果"""
    passed: bool
    reason: str
    confidence: float = 1.0
    retried: bool = False           # 是否经过容错重试后通过