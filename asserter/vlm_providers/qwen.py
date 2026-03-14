"""Qwen3-VL 通过 OpenAI 兼容 API 调用（DashScope / 自部署）"""

from __future__ import annotations

from asserter.vlm_providers._utils import guess_mime_type
from config.settings import VLMConfig


class QwenVLProvider:

    def __init__(self, config: VLMConfig):
        from openai import OpenAI
        self.client = OpenAI(base_url=config.base_url, api_key=config.api_key)
        self.model = config.model
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens

    def chat(self, system_prompt: str, image_base64: str,
             user_prompt: str) -> str:
        mime = guess_mime_type(image_base64)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{image_base64}",
                    },
                },
                {"type": "text", "text": user_prompt},
            ]},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content