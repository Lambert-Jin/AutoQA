"""Phase 3 验证脚本：测试 TestExecutor 执行能力

需要：
1. 连接 Android 设备（adb devices 能看到）
2. AutoGLM 模型服务可用（设置环境变量 AUTOGLM_BASE_URL、AUTOGLM_API_KEY）

运行：
    python tests/test_phase3.py
"""

import os
import sys

from phone_agent.device_factory import DeviceType, set_device_type, get_device_factory
from phone_agent.model.client import ModelConfig

from executor import TestExecutor, ExecutorActionResult


# ── 1. 离线测试：不需要设备和模型 ──

def test_data_model():
    """测试 ExecutorActionResult 数据类"""
    r = ExecutorActionResult(success=True, rounds=3, actions_taken=[{"action": "Tap"}])
    assert r.success is True
    assert r.rounds == 3
    assert r.error is None
    assert len(r.actions_taken) == 1
    print("✓ ExecutorActionResult 数据类测试通过\n")


def test_executor_init():
    """测试 TestExecutor 初始化"""
    config = ModelConfig(
        base_url="http://fake:8000/v1",
        api_key="fake",
        model_name="autoglm-phone-9b",
    )
    executor = TestExecutor(config, lang="cn")
    assert executor._context == []
    assert executor.max_steps == 10
    print("✓ TestExecutor 初始化测试通过\n")


def test_reset():
    """测试上下文重置"""
    config = ModelConfig(base_url="http://fake:8000/v1", api_key="fake")
    executor = TestExecutor(config)
    executor._context = [{"role": "system", "content": "test"}]
    executor.reset()
    assert executor._context == []
    print("✓ reset 测试通过\n")


# ── 2. 在线测试：需要设备 + 模型服务 ──

def test_execute_action():
    """测试单步执行：打开一个 App"""
    executor = _create_executor()

    print("  执行: 打开设置")
    result = executor.execute_action("打开手机设置")
    print(f"  结果: success={result.success}, rounds={result.rounds}, error={result.error}")
    print(f"  执行的动作: {result.actions_taken}")
    assert result.success, f"执行失败: {result.error}"
    print("✓ 单步执行测试通过\n")

    return executor


def test_context_persistence(executor: TestExecutor):
    """测试上下文保持：在上一步基础上继续操作"""
    assert len(executor._context) > 0, "上下文不应为空"

    print("  执行: 点击 WLAN（在设置页面中）")
    result = executor.execute_action("点击 WLAN 或 Wi-Fi 选项")
    print(f"  结果: success={result.success}, rounds={result.rounds}")
    assert result.success, f"执行失败: {result.error}"
    print("✓ 上下文保持测试通过\n")

    return executor


def test_handle_unexpected(executor: TestExecutor):
    """测试弹窗处理"""
    print("  执行: handle_unexpected('返回上一页')")
    success = executor.handle_unexpected("返回上一页", max_steps=3)
    print(f"  结果: success={success}")
    print("✓ handle_unexpected 测试通过\n")


def test_reset_and_new_task(executor: TestExecutor):
    """测试 reset 后执行新任务"""
    executor.reset()
    assert executor._context == [], "reset 后上下文应为空"

    print("  执行: reset 后打开计算器")
    result = executor.execute_action("返回桌面")
    print(f"  结果: success={result.success}, rounds={result.rounds}")
    print("✓ reset + 新任务测试通过\n")


def _create_executor() -> TestExecutor:
    """创建连接真实设备和模型的 TestExecutor"""
    base_url = os.environ.get("AUTOGLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    api_key = os.environ["AUTOGLM_API_KEY"]
    model = os.environ.get("AUTOGLM_MODEL", "autoglm-phone")

    set_device_type(DeviceType.ADB)

    config = ModelConfig(
        base_url=base_url,
        api_key=api_key,
        model_name=model,
    )
    return TestExecutor(config, lang="cn", max_steps_per_action=15)


if __name__ == "__main__":
    print("=" * 50)
    print("Phase 3 执行能力验证")
    print("=" * 50)

    # 离线测试（始终运行）
    print("\n── 离线测试 ──\n")
    test_data_model()
    test_executor_init()
    test_reset()

    # 在线测试（需要设备 + 模型）
    has_key = "AUTOGLM_API_KEY" in os.environ
    if not has_key:
        print("── 跳过在线测试（未设置 AUTOGLM_API_KEY）──\n")
        print("设置方法:")
        print("  export AUTOGLM_API_KEY=your-key")
        print("  export AUTOGLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4  # 可选")
    else:
        # 检查设备连接
        try:
            set_device_type(DeviceType.ADB)
            factory = get_device_factory()
            devices = factory.list_devices()
            if not devices:
                print("── 跳过在线测试（未检测到 ADB 设备）──\n")
                print("请连接 Android 设备并确保 adb devices 可见")
            else:
                print(f"\n── 在线测试（设备: {devices}）──\n")
                executor = test_execute_action()
                executor = test_context_persistence(executor)
                test_handle_unexpected(executor)
                test_reset_and_new_task(executor)
        except Exception as e:
            print(f"\n在线测试出错: {e}")
            import traceback
            traceback.print_exc()

    print("=" * 50)
    print("Phase 3 验证完成!")