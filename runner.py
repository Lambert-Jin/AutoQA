"""TestRunner：测试编排与容错重试"""

from __future__ import annotations

import logging
import time

from phone_agent.device_factory import get_device_factory

from asserter import Asserter
from config.settings import AssertResult, VLMConfig
from executor import ExecutorActionResult, TestExecutor
from screenshot import ScreenshotManager
from suite import (
    ActionStep,
    AssertStep,
    StepResult,
    TestCase,
    TestCaseResult,
    TestSuite,
    TestSuiteResult,
    Timing,
)

logger = logging.getLogger(__name__)


class TestRunner:
    """测试运行器：编排 TestCase、执行步骤、容错重试"""

    def __init__(
        self,
        executor: TestExecutor,
        asserter: Asserter,
        screenshot_mgr: ScreenshotManager | None = None,
    ):
        self.executor = executor
        self.asserter = asserter
        self.screenshot_mgr = screenshot_mgr or ScreenshotManager()

    def run_suite(self, suite: TestSuite) -> TestSuiteResult:
        """运行整个测试套件"""
        print(f"\n{'='*60}")
        print(f"  测试套件: {suite.name}")
        print(f"  用例数量: {len(suite.test_cases)}")
        print(f"{'='*60}\n")

        cases: list[TestCaseResult] = []
        for i, test_case in enumerate(suite.test_cases, 1):
            print(f"── 用例 {i}/{len(suite.test_cases)}: {test_case.name} ──\n")
            result = self.run_case(test_case)
            cases.append(result)
            self._print_case_summary(result)

        suite_result = TestSuiteResult(suite_name=suite.name, cases=cases)
        self._print_suite_summary(suite_result)
        return suite_result

    def run_case(self, case: TestCase) -> TestCaseResult:
        """运行单个测试用例"""
        self.executor.reset()

        step_results: list[StepResult] = []

        for i, step in enumerate(case.steps, 1):
            if isinstance(step, ActionStep):
                result = self._run_action(step, i)
            elif isinstance(step, AssertStep):
                result = self._run_assert(step, i)
            else:
                continue

            step_results.append(result)

            if not result.success and not case.continue_on_error:
                logger.info("步骤失败且 continueOnError=False，中断后续步骤")
                break

        status = "passed" if all(r.success for r in step_results) else "failed"
        return TestCaseResult(case_name=case.name, steps=step_results, status=status)

    def _run_action(self, step: ActionStep, step_num: int) -> StepResult:
        """执行操作步骤"""
        timing = Timing.start_now()

        print(f"  Step {step_num}: [操作] {step.description} ... ", end="", flush=True)

        result: ExecutorActionResult = self.executor.execute_action(step.description)

        timing.stop()
        duration = timing.duration_ms / 1000

        if result.success:
            print(f"OK ({result.rounds} 轮, {duration:.1f}s)")
        else:
            print(f"FAIL ({result.error})")

        return StepResult(
            step=step,
            success=result.success,
            timing=timing,
            detail=result,
        )

    def _run_assert(self, step: AssertStep, step_num: int) -> StepResult:
        """执行断言步骤，含容错重试"""
        timing = Timing.start_now()

        print(f"  Step {step_num}: [断言] {step.expectation} ... ", end="", flush=True)

        # 截图并断言
        screenshot = self.screenshot_mgr.capture(get_device_factory())
        result: AssertResult = self.asserter.verify(screenshot, step.expectation)

        # 容错：断言失败 → 清理环境 → 重试
        if not result.passed and step.retry_on_fail:
            print(f"RETRY ", end="", flush=True)
            logger.info("断言失败，尝试清理后重试: %s", step.retry_cleanup)

            self.executor.handle_unexpected(step.retry_cleanup)

            screenshot = self.screenshot_mgr.capture(get_device_factory())
            result = self.asserter.verify(screenshot, step.expectation)
            result.retried = True

        timing.stop()
        duration = timing.duration_ms / 1000

        if result.passed:
            retry_mark = "(重试后) " if result.retried else ""
            print(f"PASS {retry_mark}(confidence: {result.confidence:.2f}, {duration:.1f}s)")
        else:
            sev = f"[{step.severity}] " if step.severity != "critical" else ""
            print(f"FAIL {sev}(confidence: {result.confidence:.2f}, {duration:.1f}s)")
            print(f"           reason: {result.reason}")

        return StepResult(
            step=step,
            success=result.passed,
            timing=timing,
            detail=result,
        )

    @staticmethod
    def _print_case_summary(result: TestCaseResult):
        icon = "✅" if result.status == "passed" else "❌"
        print(f"\n  {icon} 用例结果: {result.case_name} — "
              f"{result.passed_count}/{result.total_count} passed\n")

    @staticmethod
    def _print_suite_summary(result: TestSuiteResult):
        print(f"{'='*60}")
        print(f"  测试结果: {result.passed}/{result.total} passed, "
              f"{result.failed} failed, {result.duration_ms/1000:.1f}s")
        icon = "✅" if result.failed == 0 else "❌"
        print(f"  {icon} {result.suite_name}")
        print(f"{'='*60}\n")
