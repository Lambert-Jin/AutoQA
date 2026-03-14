"""AutoQA CLI 入口"""

from __future__ import annotations

import argparse
import logging
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="autoqa",
        description="AutoQA - 基于 AutoGLM + VLM 的移动端自动化测试框架",
    )
    subparsers = parser.add_subparsers(dest="command")

    # run 子命令
    run_parser = subparsers.add_parser("run", help="运行 YAML 测试用例")
    run_parser.add_argument("yaml_path", help="YAML 测试用例文件路径")
    run_parser.add_argument("--device-type", default=None, help="设备类型: adb | hdc | ios")
    run_parser.add_argument("--device-id", default=None, help="设备 ID")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        run_test(args)


def run_test(args):
    """执行测试"""
    # 配置日志：只对 auto_qa 开 DEBUG，第三方库保持 WARNING
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    auto_qa_level = logging.DEBUG if args.verbose else logging.INFO
    logging.getLogger("auto_qa").setLevel(auto_qa_level)
    logging.getLogger("phone_agent").setLevel(
        logging.INFO if args.verbose else logging.WARNING
    )

    from phone_agent.device_factory import DeviceType, set_device_type
    from phone_agent.model.client import ModelConfig

    from asserter import Asserter
    from planner import parse_yaml
    from runner import TestRunner
    from executor import TestExecutor
    from screenshot import ScreenshotManager

    # 解析 YAML
    suite, device_config, autoglm_config, vlm_config = parse_yaml(args.yaml_path)

    # CLI 参数覆盖 YAML 配置
    if args.device_type:
        device_config.device_type = args.device_type
    if args.device_id:
        device_config.device_id = args.device_id

    # 初始化设备
    device_type_map = {
        "adb": DeviceType.ADB,
        "hdc": DeviceType.HDC,
        "ios": DeviceType.IOS,
    }
    set_device_type(device_type_map.get(device_config.device_type, DeviceType.ADB))

    # 初始化组件
    model_config = ModelConfig(
        base_url=autoglm_config.base_url,
        api_key=autoglm_config.api_key,
        model_name=autoglm_config.model,
        max_tokens=autoglm_config.max_tokens,
        temperature=autoglm_config.temperature,
    )

    executor = TestExecutor(
        model_config=model_config,
        device_id=device_config.device_id,
        lang=autoglm_config.lang,
    )
    asserter = Asserter(vlm_config)
    screenshot_mgr = ScreenshotManager()

    # 运行测试
    runner = TestRunner(executor, asserter, screenshot_mgr)
    result = runner.run_suite(suite)

    # 退出码
    sys.exit(0 if result.failed == 0 else 1)


if __name__ == "__main__":
    main()