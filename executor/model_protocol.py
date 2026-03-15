"""ActionModel 协议：所有操作模型适配器必须实现此接口"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from executor.actions import ModelOutput, UnifiedAction


@runtime_checkable
class ActionModel(Protocol):
    """操作模型协议"""

    def get_system_prompt(self) -> str:
        """返回系统提示词"""
        ...

    def build_user_message(
        self,
        text: str,
        image_base64: str | None = None,
        screen_width: int = 0,
        screen_height: int = 0,
    ) -> dict[str, Any]:
        """构建 user 消息（含截图）"""
        ...

    def build_assistant_message(self, raw_content: str) -> dict[str, Any]:
        """构建 assistant 消息（用于上下文回填）"""
        ...

    def remove_images(self, message: dict) -> dict:
        """移除消息中的图片（节省 token）"""
        ...

    def call(self, messages: list[dict]) -> ModelOutput:
        """调用模型，返回原始输出"""
        ...

    def parse(
        self,
        output: ModelOutput,
        screen_width: int,
        screen_height: int,
    ) -> UnifiedAction:
        """解析模型输出为统一动作"""
        ...