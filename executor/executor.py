"""TestExecutor：自管理对话上下文，依赖 ActionModel + Device"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from device import Device
from device.errors import ScreenshotSensitiveError
from executor.actions import ActionType, UnifiedAction
from executor.action_executor import ActionExecutor, ActionExecuteResult as _AER
from executor.model_protocol import ActionModel

logger = logging.getLogger(__name__)


@dataclass
class ExecutorActionResult:
    """单个 ActionStep 的执行结果"""
    success: bool
    actions_taken: list[dict] = field(default_factory=list)
    rounds: int = 0
    error: str | None = None


class TestExecutor:
    """
    测试执行器。

    改造后的变化（对比旧版）：
    - 不再依赖 phone_agent 的任何组件
    - 通过 ActionModel 协议适配不同模型
    - 通过 Device 协议操作设备
    - 去掉 _suppress_stdout() hack（BaseModelClient 用 logging，不 print）
    - 上下文窗口管理（防止 token 溢出）
    """

    MAX_CONTEXT_TURNS = 15  # 最多保留的对话轮次（1 轮 = 1 user + 1 assistant）

    def __init__(
        self,
        model: ActionModel,
        device: Device,
        max_steps_per_action: int = 10,
        action_cache: ActionCache | None = None,
        post_action_delay: float = 1.0,
    ):
        self.model = model
        self.device = device
        self.device_id = device.device_id
        self.action_executor = ActionExecutor(device)
        self.max_steps = max_steps_per_action
        self.action_cache = action_cache
        self.post_action_delay = post_action_delay  # 动作执行后等待页面加载的延迟（秒）
        self._context: list[dict[str, Any]] = []

    def execute_action(self, description: str, cache_key: str = "") -> ExecutorActionResult:
        """
        执行一个语义级操作步骤。

        内部多轮循环直到模型返回 finish 或达到 max_steps。
        每次调用都能注入新的任务描述到已有上下文。
        """
        actions_taken: list[dict] = []
        verbose = logger.isEnabledFor(logging.DEBUG)

        # system prompt（仅首次）
        if not self._context:
            self._context.append({
                "role": "system",
                "content": self.model.get_system_prompt(),
            })

        # 截图 + 构造消息
        screenshot = self.device.screenshot()
        current_app = self.device.current_app()

        # ── 缓存快速路径 ──
        if cache_key and self.action_cache:
            activity = self.device.current_activity()
            cached = self.action_cache.lookup(
                cache_key, current_app, activity, screenshot,
            )
            if cached:
                logger.info("缓存命中: %s (相似度 %.2f)", cache_key, cached.similarity)
                params = cached.to_action_params()
                # 归一化坐标 (0-999) → 绝对像素
                sw, sh = screenshot.width, screenshot.height
                abs_x = int(params["x"] / 999 * sw)
                abs_y = int(params["y"] / 999 * sh)
                abs_end_x = int(params["end_x"] / 999 * sw) if params.get("end_x") is not None else None
                abs_end_y = int(params["end_y"] / 999 * sh) if params.get("end_y") is not None else None
                cache_action = UnifiedAction(
                    type=ActionType(params["action_type"].lower()),
                    x=abs_x, y=abs_y,
                    end_x=abs_end_x,
                    end_y=abs_end_y,
                )
                cache_result = self.action_executor.execute(cache_action)
                if cache_result.success:
                    self.action_cache.record_hit(cached.entry)
                    return ExecutorActionResult(
                        success=True,
                        actions_taken=[{"type": params["action_type"], "x": params["x"], "y": params["y"]}],
                        rounds=0,
                    )
                logger.warning("缓存动作执行失败，fallback 到正常流程")
            else:
                logger.info("缓存未命中: %s (app=%s, activity=%s)", cache_key, current_app, activity)
        initial_screenshot = screenshot  # 缓存写回用
        screen_info = self.model.build_screen_info(current_app)

        self._context.append(
            self.model.build_user_message(
                text=f"{description}\n\n{screen_info}",
                image_base64=screenshot.base64_data,
                screen_width=screenshot.width,
                screen_height=screenshot.height,
            )
        )

        for round_num in range(self.max_steps):
            if verbose:
                self._log_request(round_num + 1)

            # 调用模型
            try:
                output = self.model.call(self._context)
            except Exception as e:
                logger.error("模型调用失败: %s", e)
                return ExecutorActionResult(
                    success=False, actions_taken=actions_taken,
                    rounds=round_num + 1, error=f"Model error: {e}",
                )

            # 解析为 UnifiedAction
            action = self.model.parse(output, screenshot.width, screenshot.height)

            if verbose:
                self._log_response(round_num + 1, action, output)

            # 更新上下文：移除旧图片 + 添加 assistant 回复
            self._context[-1] = self.model.remove_images(self._context[-1])
            self._context.append(
                self.model.build_assistant_message(output.raw_content)
            )

            # finish → 步骤完成
            if action.is_finish:
                logger.info("步骤完成: %s (共 %d 轮)", description, round_num + 1)
                exec_result = ExecutorActionResult(
                    success=True, actions_taken=actions_taken,
                    rounds=round_num + 1,
                )
                self._maybe_cache_action(
                    cache_key, exec_result, actions_taken,
                    current_app, initial_screenshot,
                )
                return exec_result

            # 执行动作
            result = self.action_executor.execute(action)
            actions_taken.append({
                "type": action.type.value,
                "x": action.x, "y": action.y,
                "end_x": action.end_x, "end_y": action.end_y,
            })

            if result.should_finish:
                exec_result = ExecutorActionResult(
                    success=result.success, actions_taken=actions_taken,
                    rounds=round_num + 1, error=result.message,
                )
                self._maybe_cache_action(
                    cache_key, exec_result, actions_taken,
                    current_app, initial_screenshot,
                )
                return exec_result

            # 上下文窗口管理（防止 token 溢出）
            self._trim_context()

            # 等待页面加载后再截图
            if self.post_action_delay > 0:
                time.sleep(self.post_action_delay)

            # 下一轮截图
            try:
                screenshot = self.device.screenshot()
            except ScreenshotSensitiveError:
                # 敏感屏幕（支付/安全页面）：使用上次的截图尺寸，不发图片
                current_app = self.device.current_app()
                screen_info = self.model.build_screen_info(current_app)
                self._context.append(
                    self.model.build_user_message(
                        text=f"** Screen Info **\n{screen_info}\n"
                             "⚠️ 当前页面截图受限（可能是支付/安全页面），请根据之前的上下文继续操作",
                    )
                )
                continue

            current_app = self.device.current_app()
            screen_info = self.model.build_screen_info(current_app)

            self._context.append(
                self.model.build_user_message(
                    text=f"** Screen Info **\n{screen_info}",
                    image_base64=screenshot.base64_data,
                    screen_width=screenshot.width,
                    screen_height=screenshot.height,
                )
            )

        return ExecutorActionResult(
            success=False, actions_taken=actions_taken,
            rounds=self.max_steps, error="max_steps exceeded",
        )

    def handle_unexpected(
        self,
        instruction: str = "关闭当前弹窗或广告",
        max_steps: int = 3,
    ) -> bool:
        """处理意外情况（弹窗、广告等）"""
        original_max = self.max_steps
        self.max_steps = max_steps
        result = self.execute_action(instruction)
        self.max_steps = original_max
        return result.success

    def reset(self):
        """重置上下文（切换 TestCase 时调用）"""
        self._context = []
        logger.debug("Executor 上下文已重置")

    def _maybe_cache_action(
        self,
        cache_key: str,
        result: ExecutorActionResult,
        actions_taken: list[dict],
        app: str,
        screenshot,
    ):
        """成功且仅执行 1 个动作时写入缓存（多动作操作不缓存）"""
        if not cache_key or not self.action_cache:
            return
        if not result.success or len(actions_taken) != 1:
            return

        first = actions_taken[0]

        # 无坐标的动作（launch/back/home 等）不缓存
        if first["x"] is None or first["y"] is None:
            return

        activity = self.device.current_activity()

        # 绝对像素坐标 → 归一化坐标 (0-999)
        sw, sh = screenshot.width, screenshot.height
        x_norm = int(first["x"] / sw * 999) if sw else first["x"]
        y_norm = int(first["y"] / sh * 999) if sh else first["y"]
        end_x_norm = int(first["end_x"] / sw * 999) if first.get("end_x") and sw else first.get("end_x")
        end_y_norm = int(first["end_y"] / sh * 999) if first.get("end_y") and sh else first.get("end_y")

        try:
            self.action_cache.store_action(
                cache_key=cache_key,
                app=app,
                activity=activity,
                action_type=first["type"],
                x=x_norm,
                y=y_norm,
                end_x=end_x_norm,
                end_y=end_y_norm,
                screenshot=screenshot,
            )
            logger.info("已写入缓存: %s (action=%s, x=%d, y=%d, app=%s, activity=%s)",
                        cache_key, first["type"], x_norm, y_norm, app, activity)
        except Exception as e:
            logger.warning("缓存写入失败: %s", e)

    def _trim_context(self):
        """
        上下文窗口管理：保留 system prompt + 最近 N 轮对话，防止 token 溢出。
        """
        if not self._context:
            return

        system = [self._context[0]] if self._context[0].get("role") == "system" else []
        messages = self._context[len(system):]

        max_messages = self.MAX_CONTEXT_TURNS * 2
        if len(messages) > max_messages:
            trimmed = len(messages) - max_messages
            logger.debug("裁剪上下文：移除 %d 条旧消息，保留最近 %d 轮",
                         trimmed, self.MAX_CONTEXT_TURNS)
            messages = messages[-max_messages:]
            self._context = system + messages

    def _log_request(self, round_num: int):
        last_user = next(
            (m for m in reversed(self._context) if m.get("role") == "user"), None
        )
        if last_user:
            content = last_user.get("content", "")
            if isinstance(content, list):
                text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
            else:
                text = str(content)
            logger.debug(
                "📤 Round %d | 指令: %s | 上下文: %d 条消息",
                round_num, text[:100], len(self._context),
            )

    @staticmethod
    def _log_response(round_num: int, action: UnifiedAction, output):
        thinking = output.thinking[:200] + "..." if len(output.thinking) > 200 else output.thinking
        logger.debug(
            "📥 Round %d | 思考: %s | 动作: %s (%s, %s)",
            round_num, thinking, action.type.value, action.x, action.y,
        )
