"""TestExecutor：复用 Open-AutoGLM 组件，自管理对话上下文"""

from __future__ import annotations

import io
import logging
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from phone_agent.actions.handler import ActionHandler, ActionResult, parse_action
from phone_agent.config import get_system_prompt
from phone_agent.device_factory import DeviceFactory, get_device_factory
from phone_agent.model.client import (
    MessageBuilder,
    ModelClient,
    ModelConfig,
    ModelResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutorActionResult:
    """单个 ActionStep 的执行结果"""
    success: bool
    actions_taken: list[dict] = field(default_factory=list)
    rounds: int = 0
    error: str | None = None


@contextmanager
def _suppress_stdout():
    """抑制 stdout 输出（用于屏蔽 Open-AutoGLM 的 print）"""
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old_stdout


class TestExecutor:
    """
    测试执行器：复用 Open-AutoGLM 的组件，自己管理对话上下文。

    与 PhoneAgent 的区别：
    1. 多个 ActionStep 共享同一个上下文（不 reset）
    2. 每个新步骤都能注入新的任务描述
    3. 支持 handle_unexpected() 处理意外情况
    """

    def __init__(
        self,
        model_config: ModelConfig,
        device_id: str | None = None,
        lang: str = "cn",
        max_steps_per_action: int = 10,
    ):
        # 复用 Open-AutoGLM 组件
        self.model_client = ModelClient(model_config)
        self.action_handler = ActionHandler(device_id=device_id)
        self.device_id = device_id
        self.system_prompt = get_system_prompt(lang)
        self.max_steps = max_steps_per_action
        self._verbose = logger.isEnabledFor(logging.DEBUG)

        # 自管理上下文（整个 TestCase 共享）
        self._context: list[dict[str, Any]] = []

    def execute_action(self, description: str) -> ExecutorActionResult:
        """
        执行一个语义级操作步骤。

        与 PhoneAgent.step() 的关键区别：
        - 每次调用都能注入新的任务描述到已有上下文
        - 内部多轮循环直到 AutoGLM 返回 finish
        - 不会 reset 上下文

        Args:
            description: 操作步骤描述，如 "点击第一篇文章"
        """
        device_factory = get_device_factory()
        actions_taken: list[dict] = []
        verbose = self._verbose

        # 初始化 system prompt（仅首次）
        if not self._context:
            self._context.append(
                MessageBuilder.create_system_message(self.system_prompt)
            )

        # 第一轮：注入新的操作指令 + 截图
        screenshot = device_factory.get_screenshot(self.device_id)
        current_app = device_factory.get_current_app(self.device_id)
        screen_info = MessageBuilder.build_screen_info(current_app)

        self._context.append(
            MessageBuilder.create_user_message(
                text=f"{description}\n\n{screen_info}",
                image_base64=screenshot.base64_data,
            )
        )

        for round_num in range(self.max_steps):
            # verbose: 打印请求概要
            if verbose:
                self._log_request(round_num + 1)

            # 调用 AutoGLM（抑制其 print 输出）
            try:
                with _suppress_stdout():
                    response: ModelResponse = self.model_client.request(self._context)
            except Exception as e:
                logger.error("模型调用失败: %s", e)
                return ExecutorActionResult(
                    success=False,
                    actions_taken=actions_taken,
                    rounds=round_num + 1,
                    error=f"Model error: {e}",
                )

            # verbose: 打印响应
            if verbose:
                self._log_response(round_num + 1, response)

            # 解析动作（抑制 parse_action 的 print）
            try:
                with _suppress_stdout():
                    action = parse_action(response.action)
            except ValueError:
                action = {"_metadata": "finish", "message": response.action}

            # 移除旧图片，添加 assistant 回复
            self._context[-1] = MessageBuilder.remove_images_from_message(
                self._context[-1]
            )
            self._context.append(
                MessageBuilder.create_assistant_message(
                    f"<think>{response.thinking}</think>"
                    f"<answer>{response.action}</answer>"
                )
            )

            # finish → 步骤完成
            if action.get("_metadata") == "finish":
                logger.info("步骤完成: %s (共 %d 轮)", description, round_num + 1)
                return ExecutorActionResult(
                    success=True,
                    actions_taken=actions_taken,
                    rounds=round_num + 1,
                )

            # 执行动作
            try:
                result: ActionResult = self.action_handler.execute(
                    action, screenshot.width, screenshot.height
                )
            except Exception as e:
                logger.error("动作执行失败: %s", e)
                return ExecutorActionResult(
                    success=False,
                    actions_taken=actions_taken,
                    rounds=round_num + 1,
                    error=f"Action error: {e}",
                )

            actions_taken.append(action)

            if result.should_finish:
                return ExecutorActionResult(
                    success=result.success,
                    actions_taken=actions_taken,
                    rounds=round_num + 1,
                    error=result.message,
                )

            # 下一轮：只发截图和 screen_info，不发新指令
            screenshot = device_factory.get_screenshot(self.device_id)
            current_app = device_factory.get_current_app(self.device_id)
            screen_info = MessageBuilder.build_screen_info(current_app)

            self._context.append(
                MessageBuilder.create_user_message(
                    text=f"** Screen Info **\n\n{screen_info}",
                    image_base64=screenshot.base64_data,
                )
            )

        return ExecutorActionResult(
            success=False,
            actions_taken=actions_taken,
            rounds=self.max_steps,
            error="max_steps exceeded",
        )

    def _log_request(self, round_num: int):
        """打印本轮发送给模型的消息概要"""
        print(f"\n    {'─' * 50}")
        print(f"    📤 请求 (Round {round_num})")
        print(f"    {'─' * 50}")

        # 只打印最后一条 user 消息（当前轮的输入）
        for msg in reversed(self._context):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    img_count = sum(1 for c in content if c.get("type") == "image_url")
                    print(f"    指令: {' '.join(texts)}")
                    if img_count:
                        print(f"    截图: {img_count} 张")
                else:
                    print(f"    指令: {content}")
                break

        print(f"    上下文消息数: {len(self._context)}")

    @staticmethod
    def _log_response(round_num: int, response: ModelResponse):
        """打印模型返回的响应"""
        print(f"\n    📥 响应 (Round {round_num})")
        print(f"    {'─' * 50}")
        # thinking 截断显示
        thinking = response.thinking.strip()
        if len(thinking) > 200:
            thinking = thinking[:200] + "..."
        print(f"    思考: {thinking}")
        print(f"    动作: {response.action}")
        print(f"    {'─' * 50}")

    def handle_unexpected(
        self,
        instruction: str = "关闭当前弹窗或广告",
        max_steps: int = 3,
    ) -> bool:
        """
        处理意外情况（弹窗、广告等）。

        向已有上下文注入清理指令，让 AutoGLM 处理干扰后继续。
        """
        original_max = self.max_steps
        self.max_steps = max_steps
        result = self.execute_action(instruction)
        self.max_steps = original_max
        return result.success

    def reset(self):
        """重置上下文（切换 TestCase 时调用）"""
        self._context = []
        self._verbose = logger.isEnabledFor(logging.DEBUG)
        logger.debug("Executor 上下文已重置")