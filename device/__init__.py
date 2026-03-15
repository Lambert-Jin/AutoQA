"""设备抽象层：统一设备接口 + 工厂函数"""

from device.base import Device, DeviceType, DeviceScreenshot
from device.errors import (
    DeviceError, DeviceConnectionError,
    ScreenshotError, ScreenshotSensitiveError,
    ActionExecutionError, ModelCallError,
)


def create_device(device_type: DeviceType, device_id: str | None = None) -> Device:
    """设备工厂。扩展新平台时只需新增分支 + 对应实现类。"""
    if device_type == DeviceType.ADB:
        from device.adb import ADBDevice
        return ADBDevice(device_id)
    else:
        raise ValueError(f"不支持的设备类型: {device_type}")


__all__ = [
    "Device", "DeviceType", "DeviceScreenshot",
    "DeviceError", "DeviceConnectionError",
    "ScreenshotError", "ScreenshotSensitiveError",
    "ActionExecutionError", "ModelCallError",
    "create_device",
]