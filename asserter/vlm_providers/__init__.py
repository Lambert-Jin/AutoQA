"""VLM Provider 协议与工厂函数"""

from __future__ import annotations

from typing import Protocol

from config.settings import VLMConfig


class VLMProvider(Protocol):
    """VLM 提供者协议：统一不同模型的调用接口"""

    def chat(self, system_prompt: str, image_base64: str,
             user_prompt: str) -> str:
        """发送图文请求，返回模型原始文本响应"""
        ...


def create_vlm_provider(config: VLMConfig) -> VLMProvider:
    """工厂函数：根据 provider 配置创建对应的 VLM 实例"""
    from asserter.vlm_providers.gemini import GeminiProvider
    from asserter.vlm_providers.qwen import QwenVLProvider

    providers: dict[str, type] = {
        "qwen": QwenVLProvider,
        "gemini": GeminiProvider,
    }
    cls = providers.get(config.provider)
    if cls is None:
        raise ValueError(
            f"Unknown VLM provider: {config.provider}, "
            f"supported: {list(providers.keys())}"
        )
    return cls(config)