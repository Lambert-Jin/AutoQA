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

    # generate 子命令
    gen_parser = subparsers.add_parser("generate", help="自然语言生成 YAML 测试用例")
    gen_parser.add_argument("description", help="自然语言测试描述")
    gen_parser.add_argument("-o", "--output", default=None, help="输出 YAML 文件路径（不指定则输出到终端）")
    gen_parser.add_argument("--device-type", default="android", help="设备类型: android | harmony | ios")
    gen_parser.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")

    # interactive 子命令
    int_parser = subparsers.add_parser("interactive", help="交互式测试模式")
    int_parser.add_argument("--device-type", default=None, help="设备类型: adb | hdc | ios")
    int_parser.add_argument("--device-id", default=None, help="设备 ID")
    int_parser.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        run_test(args)
    elif args.command == "generate":
        generate_test(args)
    elif args.command == "interactive":
        interactive_test(args)


def _setup_logging(verbose: bool):
    """配置日志：只对项目模块开 DEBUG，第三方库保持 WARNING"""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    level = logging.DEBUG if verbose else logging.INFO
    logging.getLogger("auto_qa").setLevel(level)
    logging.getLogger("planner").setLevel(level)
    logging.getLogger("phone_agent").setLevel(
        logging.INFO if verbose else logging.WARNING
    )


def run_test(args):
    """模式 1：执行 YAML 测试用例"""
    _setup_logging(args.verbose)

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


def generate_test(args):
    """模式 2：自然语言 → 生成 YAML 文件"""
    _setup_logging(args.verbose)

    from config.settings import PlannerConfig
    from planner import plan_test_case, generate_yaml_content

    planner_config = PlannerConfig()

    print(f"\n规划中: {args.description}\n")

    try:
        test_case = plan_test_case(args.description, planner_config)
    except ValueError as e:
        print(f"规划失败: {e}", file=sys.stderr)
        sys.exit(1)

    yaml_content = generate_yaml_content(
        test_case,
        device_type=args.device_type,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(yaml_content)
        print(f"已生成: {args.output}")
        print(f"  用例名: {test_case.name}")
        print(f"  步骤数: {len(test_case.steps)}")
        print(f"\n可通过以下命令执行:")
        print(f"  python main.py run {args.output}")
    else:
        print("--- 生成的 YAML ---\n")
        print(yaml_content)

    # 打印步骤预览
    _print_steps_preview(test_case)


def interactive_test(args):
    """模式 3：交互式测试"""
    _setup_logging(args.verbose)

    from phone_agent.device_factory import DeviceType, set_device_type
    from phone_agent.model.client import ModelConfig

    from asserter import Asserter
    from config.settings import AutoGLMConfig, PlannerConfig, VLMConfig
    from planner import plan_test_case
    from runner import TestRunner
    from executor import TestExecutor
    from screenshot import ScreenshotManager
    from suite import TestSuite

    # 使用默认配置（环境变量）
    autoglm_config = AutoGLMConfig()
    vlm_config = VLMConfig()
    planner_config = PlannerConfig()

    # 初始化设备
    device_type = args.device_type or "adb"
    device_type_map = {
        "adb": DeviceType.ADB,
        "hdc": DeviceType.HDC,
        "ios": DeviceType.IOS,
    }
    set_device_type(device_type_map.get(device_type, DeviceType.ADB))

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
        device_id=args.device_id,
        lang=autoglm_config.lang,
    )
    asserter = Asserter(vlm_config)
    screenshot_mgr = ScreenshotManager()
    runner = TestRunner(executor, asserter, screenshot_mgr)

    print("\n" + "=" * 60)
    print("  AutoQA 交互式测试模式")
    print("  输入自然语言描述测试步骤和预期结果")
    print("  输入 quit 或 exit 退出")
    print("=" * 60)

    round_num = 0
    while True:
        round_num += 1
        print(f"\n── 第 {round_num} 轮 ──")

        try:
            description = input("\n请描述测试场景: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            break

        if not description or description.lower() in ("quit", "exit", "q"):
            print("再见!")
            break

        # 规划
        print(f"\n规划中...\n")
        try:
            test_case = plan_test_case(description, planner_config)
        except ValueError as e:
            print(f"规划失败: {e}")
            continue

        _print_steps_preview(test_case)

        # 确认执行
        try:
            confirm = input("\n是否执行? (Y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            break

        if confirm in ("n", "no"):
            print("已跳过")
            continue

        # 执行
        suite = TestSuite(name=f"交互测试-{round_num}", test_cases=[test_case])
        result = runner.run_suite(suite)

        if result.failed == 0:
            print("\n所有测试通过!")
        else:
            print(f"\n{result.failed}/{result.total} 个步骤失败")


def _print_steps_preview(test_case):
    """打印步骤预览"""
    print(f"\n  用例: {test_case.name}")
    print(f"  步骤:")
    for i, step in enumerate(test_case.steps, 1):
        from suite import ActionStep, AssertStep
        if isinstance(step, ActionStep):
            print(f"    {i}. [操作] {step.description}")
        elif isinstance(step, AssertStep):
            sev = f" ({step.severity})" if step.severity != "critical" else ""
            print(f"    {i}. [断言] {step.expectation}{sev}")


if __name__ == "__main__":
    main()