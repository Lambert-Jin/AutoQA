"""YAML 测试用例解析器"""

from __future__ import annotations

import os
import re

import yaml

from config.settings import ActionModelConfig, DeviceConfig, VLMConfig
from suite import ActionStep, AssertStep, Step, TestCase, TestSuite


def _resolve_env_vars(value: str) -> str:
    """将 ${VAR} 替换为环境变量值，缺失时保留原文"""
    def _replace(match: re.Match) -> str:
        return os.environ.get(match.group(1), match.group(0))
    return re.sub(r"\$\{(\w+)\}", _replace, value)


def _resolve_dict(data: dict) -> dict:
    """递归解析字典中所有字符串的环境变量"""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = _resolve_env_vars(value)
        elif isinstance(value, dict):
            result[key] = _resolve_dict(value)
        elif isinstance(value, list):
            result[key] = [_resolve_dict(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value
    return result


def parse_yaml(path: str) -> tuple[TestSuite, DeviceConfig, ActionModelConfig, VLMConfig]:
    """
    解析 YAML 测试用例文件。

    Returns:
        (TestSuite, DeviceConfig, ActionModelConfig, VLMConfig)
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    raw = _resolve_dict(raw)

    # 解析 device 配置
    device_raw = raw.get("device", {})
    device_config = DeviceConfig(
        device_type=_map_device_type(device_raw.get("type", "android")),
        device_id=device_raw.get("id"),
    )

    # 解析 config
    config_raw = raw.get("config", {})

    model_raw = config_raw.get("action_model", {})
    model_config = ActionModelConfig(
        provider=model_raw.get("provider", ActionModelConfig.provider),
        base_url=model_raw.get("base_url", ActionModelConfig.base_url),
        api_key=model_raw.get("api_key", ActionModelConfig.api_key),
        model=model_raw.get("model", ActionModelConfig.model),
        max_tokens=model_raw.get("max_tokens", ActionModelConfig.max_tokens),
        temperature=model_raw.get("temperature", ActionModelConfig.temperature),
        lang=model_raw.get("lang", "cn"),
        custom_rules=model_raw.get("custom_rules", []),
    )

    vlm_raw = config_raw.get("vlm", {})
    vlm_config = VLMConfig(
        provider=vlm_raw.get("provider", VLMConfig.provider),
        base_url=vlm_raw.get("base_url", VLMConfig.base_url),
        api_key=vlm_raw.get("api_key", VLMConfig.api_key),
        model=vlm_raw.get("model", VLMConfig.model),
    )

    # 解析 tasks
    test_cases: list[TestCase] = []
    for task_raw in raw.get("tasks", []):
        case = _parse_test_case(task_raw)
        test_cases.append(case)

    suite = TestSuite(
        name=raw.get("name", os.path.basename(path)),
        test_cases=test_cases,
    )

    return suite, device_config, model_config, vlm_config


def _parse_test_case(raw: dict) -> TestCase:
    """解析单个 TestCase"""
    steps: list[Step] = []
    for step_raw in raw.get("flow", []):
        if "action" in step_raw:
            steps.append(ActionStep(
                description=step_raw["action"],
                timeout=step_raw.get("timeout", 30),
            ))
        elif "assert" in step_raw:
            steps.append(AssertStep(
                expectation=step_raw["assert"],
                severity=step_raw.get("severity", "critical"),
                retry_on_fail=step_raw.get("retryOnFail", False),
                retry_cleanup=step_raw.get("retryCleanup", "关闭当前弹窗或广告"),
            ))

    return TestCase(
        name=raw.get("name", "unnamed"),
        steps=steps,
        continue_on_error=raw.get("continueOnError", False),
        description=raw.get("description", ""),
    )


def _map_device_type(device_type: str) -> str:
    """映射 YAML 中的设备类型到 DeviceConfig 的值"""
    mapping = {
        "android": "adb",
        "harmony": "hdc",
        "ios": "ios",
        "adb": "adb",
        "hdc": "hdc",
    }
    return mapping.get(device_type, "adb")