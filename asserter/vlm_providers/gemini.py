"""Gemini Pro 通过 Google GenAI SDK 调用"""

from __future__ import annotations

from config.settings import VLMConfig


class GeminiProvider:

    def __init__(self, config: VLMConfig):
        from google import genai
        self.client = genai.Client(api_key=config.api_key)
        self.model = config.model
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens

    def chat(self, system_prompt: str, image_base64: str,
             user_prompt: str) -> str:
        import base64

        from google.genai import types

        from asserter.vlm_providers._utils import guess_mime_type

        image_bytes = base64.b64decode(image_base64)
        mime = guess_mime_type(image_base64)

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime),
                types.Part.from_text(text=user_prompt),
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            ),
        )
        return response.text