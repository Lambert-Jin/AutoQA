"""设备层自定义异常体系"""


class DeviceError(Exception):
    """设备层基础异常"""
    pass


class DeviceConnectionError(DeviceError):
    """设备连接失败（USB 断开、ADB 无响应）"""
    pass


class ScreenshotError(DeviceError):
    """截图失败（非敏感屏幕原因，如设备无响应）"""
    pass


class ScreenshotSensitiveError(ScreenshotError):
    """敏感屏幕截图受限（支付页面等安全限制）"""
    pass


class ActionExecutionError(Exception):
    """动作执行失败"""
    pass


class ModelCallError(Exception):
    """模型调用失败"""
    pass