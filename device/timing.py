"""操作延时配置：支持环境变量覆盖，替代 phone_agent 中 hardcoded sleep"""

import os
from dataclasses import dataclass


def _env_float(key: str, default: float) -> float:
    """从环境变量读取浮点数配置"""
    return float(os.environ.get(key, default))


@dataclass
class ActionTiming:
    """文字输入相关延时"""
    keyboard_switch_delay: float = 1.0
    text_clear_delay: float = 1.0
    text_input_delay: float = 1.0
    keyboard_restore_delay: float = 1.0

    def __post_init__(self):
        self.keyboard_switch_delay = _env_float("AQA_KEYBOARD_SWITCH_DELAY", self.keyboard_switch_delay)
        self.text_clear_delay = _env_float("AQA_TEXT_CLEAR_DELAY", self.text_clear_delay)
        self.text_input_delay = _env_float("AQA_TEXT_INPUT_DELAY", self.text_input_delay)
        self.keyboard_restore_delay = _env_float("AQA_KEYBOARD_RESTORE_DELAY", self.keyboard_restore_delay)


@dataclass
class DeviceTiming:
    """设备操作延时"""
    tap_delay: float = 0.8
    double_tap_delay: float = 0.8
    double_tap_interval: float = 0.1
    long_press_delay: float = 0.8
    swipe_delay: float = 1.0
    back_delay: float = 0.5
    home_delay: float = 0.5
    launch_delay: float = 1.5

    def __post_init__(self):
        self.tap_delay = _env_float("AQA_TAP_DELAY", self.tap_delay)
        self.double_tap_delay = _env_float("AQA_DOUBLE_TAP_DELAY", self.double_tap_delay)
        self.double_tap_interval = _env_float("AQA_DOUBLE_TAP_INTERVAL", self.double_tap_interval)
        self.long_press_delay = _env_float("AQA_LONG_PRESS_DELAY", self.long_press_delay)
        self.swipe_delay = _env_float("AQA_SWIPE_DELAY", self.swipe_delay)
        self.back_delay = _env_float("AQA_BACK_DELAY", self.back_delay)
        self.home_delay = _env_float("AQA_HOME_DELAY", self.home_delay)
        self.launch_delay = _env_float("AQA_LAUNCH_DELAY", self.launch_delay)


@dataclass
class ConnectionTiming:
    """ADB 连接相关延时"""
    adb_restart_delay: float = 2.0
    server_restart_delay: float = 1.0

    def __post_init__(self):
        self.adb_restart_delay = _env_float("AQA_ADB_RESTART_DELAY", self.adb_restart_delay)
        self.server_restart_delay = _env_float("AQA_SERVER_RESTART_DELAY", self.server_restart_delay)


@dataclass
class TimingConfig:
    """主延时配置，组合所有子配置"""
    action: ActionTiming
    device: DeviceTiming
    connection: ConnectionTiming

    def __init__(self):
        self.action = ActionTiming()
        self.device = DeviceTiming()
        self.connection = ConnectionTiming()


# 全局实例
TIMING = TimingConfig()