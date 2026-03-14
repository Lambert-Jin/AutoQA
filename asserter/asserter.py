"""基于 VLM 的视觉断言引擎"""

from __future__ import annotations

import json
import logging
import re

from asserter.prompts import ASSERT_SYSTEM_PROMPT
from asserter.vlm_providers import create_vlm_provider
from config.settings import AssertResult, Screenshot, VLMConfig

logger = logging.getLogger(__name__)


class Asserter:
    """基于 VLM 的视觉断言引擎，支持可插拔的模型后端"""

    def __init__(self, vlm_config: VLMConfig):
        self.provider = create_vlm_provider(vlm_config)

    def verify(self, screenshot: Screenshot, expectation: str) -> AssertResult:
        """对截图执行视觉断言，返回结构化结果"""
        raw = self.provider.chat(
            system_prompt=ASSERT_SYSTEM_PROMPT,
            image_base64=screenshot.base64,
            user_prompt=f"请判断以下期望是否成立：\n{expectation}",
        )

        logger.debug("VLM 原始响应: %s", raw)
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> AssertResult:
        """解析 VLM 响应为 AssertResult，容忍 markdown 代码块包裹"""
        # 去掉可能的 ```json ... ``` 包裹
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("VLM 响应 JSON 解析失败，原始内容: %s", raw)
            return AssertResult(
                passed=False,
                reason=f"VLM 响应解析失败: {raw[:200]}",
                confidence=0.0,
            )

        return AssertResult(
            passed=bool(data.get("passed", False)),
            reason=str(data.get("reason", "")),
            confidence=float(data.get("confidence", 0.0)),
        )