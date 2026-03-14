"""LLM 规划器：自然语言 → 测试步骤"""

from __future__ import annotations

import json
import logging
import re

import yaml

from config.settings import PlannerConfig
from planner.prompts import PLANNER_SYSTEM_PROMPT
from suite import ActionStep, AssertStep, Step, TestCase, TestSuite

logger = logging.getLogger(__name__)


def plan_test_case(description: str, planner_config: PlannerConfig) -> TestCase:
    """
    将自然语言描述转换为 TestCase。

    Args:
        description: 自然语言测试描述
        planner_config: 规划器 LLM 配置

    Returns:
        解析后的 TestCase
    """
    response = _call_llm(PLANNER_SYSTEM_PROMPT, description, planner_config)
    return _parse_plan_response(response)


def generate_yaml_content(
    test_case: TestCase,
    suite_name: str = "",
    device_type: str = "android",
) -> str:
    """
    将 TestCase 转换为完整的 YAML 文件内容。

    使用环境变量占位符，用户可在生成后编辑配置。
    """
    suite_name = suite_name or test_case.name

    data = {
        "name": suite_name,
        "device": {"type": device_type},
        "config": {
            "autoglm": {
                "base_url": "${AUTOGLM_BASE_URL}",
                "api_key": "${AUTOGLM_API_KEY}",
                "model": "autoglm-phone",
            },
            "vlm": {
                "provider": "gemini",
                "api_key": "${GEMINI_API_KEY}",
                "model": "gemini-2.5-flash",
            },
        },
        "tasks": [_test_case_to_dict(test_case)],
    }

    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _test_case_to_dict(case: TestCase) -> dict:
    """将 TestCase 转为 YAML 兼容的字典"""
    flow = []
    for step in case.steps:
        if isinstance(step, ActionStep):
            item = {"action": step.description}
            if step.timeout != 30:
                item["timeout"] = step.timeout
        elif isinstance(step, AssertStep):
            item = {"assert": step.expectation}
            if step.severity != "critical":
                item["severity"] = step.severity
            if step.retry_on_fail:
                item["retryOnFail"] = True
                item["retryCleanup"] = step.retry_cleanup
        else:
            continue
        flow.append(item)

    return {"name": case.name, "flow": flow}


def _call_llm(system_prompt: str, user_prompt: str, config: PlannerConfig) -> str:
    """调用 LLM 进行文本生成（不需要图片）"""
    if config.provider == "gemini":
        return _call_gemini(system_prompt, user_prompt, config)
    elif config.provider == "qwen":
        return _call_qwen(system_prompt, user_prompt, config)
    else:
        raise ValueError(f"Unsupported provider for planner: {config.provider}")


def _call_gemini(system_prompt: str, user_prompt: str, config: PlannerConfig) -> str:
    """通过 Google GenAI SDK 调用 Gemini"""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.api_key)
    response = client.models.generate_content(
        model=config.model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
        ),
    )
    return response.text


def _call_qwen(system_prompt: str, user_prompt: str, config: PlannerConfig) -> str:
    """通过 OpenAI 兼容 API 调用 Qwen"""
    from openai import OpenAI

    client = OpenAI(base_url=config.base_url, api_key=config.api_key)
    response = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    return response.choices[0].message.content


def _parse_plan_response(response: str) -> TestCase:
    """解析 LLM 返回的 JSON 为 TestCase"""
    # 去除 markdown 代码块包裹
    text = response.strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("LLM 返回的 JSON 解析失败: %s\n原文: %s", e, response)
        raise ValueError(f"LLM 返回格式错误，无法解析为 JSON: {e}") from e

    name = data.get("name", "unnamed")
    steps: list[Step] = []

    for item in data.get("flow", []):
        if "action" in item:
            steps.append(ActionStep(
                description=item["action"],
                timeout=item.get("timeout", 30),
            ))
        elif "assert" in item:
            steps.append(AssertStep(
                expectation=item["assert"],
                severity=item.get("severity", "critical"),
                retry_on_fail=item.get("retryOnFail", False),
                retry_cleanup=item.get("retryCleanup", "关闭当前弹窗或广告"),
            ))

    return TestCase(name=name, steps=steps, description="")