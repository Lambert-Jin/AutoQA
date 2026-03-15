"""统一命令执行器：封装 subprocess，统一超时/重试/日志"""

import logging
import subprocess
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class CommandRunner:
    """
    统一的 shell 命令执行器。

    改进点（对比 phone_agent）：
    - 统一超时控制
    - 失败自动重试
    - 结构化日志（不 print）
    - 可 mock 测试
    """

    def __init__(self, prefix: list[str] | None = None):
        """
        Args:
            prefix: 命令前缀，如 ["adb", "-s", "device_id"]
        """
        self.prefix = prefix or []

    def run(
        self,
        args: list[str],
        timeout: int = 10,
        retries: int = 0,
        retry_delay: float = 1.0,
    ) -> CommandResult:
        """执行命令，返回 CommandResult，支持重试"""
        cmd = self.prefix + args
        result = CommandResult(returncode=-1, stdout="", stderr="")

        for attempt in range(retries + 1):
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                result = CommandResult(
                    returncode=proc.returncode,
                    stdout=proc.stdout.strip(),
                    stderr=proc.stderr.strip(),
                )
                if result.success:
                    return result
                logger.warning(
                    "命令失败 (attempt %d/%d): %s → %s",
                    attempt + 1, retries + 1, " ".join(cmd), result.stderr,
                )
            except subprocess.TimeoutExpired:
                logger.warning(
                    "命令超时 (attempt %d/%d): %s",
                    attempt + 1, retries + 1, " ".join(cmd),
                )
                result = CommandResult(returncode=-1, stdout="", stderr="timeout")

            if attempt < retries:
                time.sleep(retry_delay)

        return result

    def run_bytes(
        self,
        args: list[str],
        timeout: int = 10,
    ) -> bytes:
        """执行命令，返回原始字节（用于截图）"""
        cmd = self.prefix + args
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"命令失败: {' '.join(cmd)}\n{proc.stderr.decode()}")
        return proc.stdout