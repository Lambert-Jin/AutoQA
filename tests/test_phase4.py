"""Phase 4 验证脚本：端到端测试编排

离线测试：验证数据模型、YAML 解析、CLI 参数解析
在线测试：需要 ADB 设备 + AutoGLM API + VLM API

运行：
    # 离线测试
    python tests/test_phase4.py

    # 端到端测试
    export AUTOGLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
    export AUTOGLM_API_KEY=your-key
    export GEMINI_API_KEY=your-key
    python main.py run examples/toutiao_comment.yaml -v
"""

import os
import sys
import time

from suite import (
    ActionStep, AssertStep, TestCase, TestSuite,
    Timing, StepResult, TestCaseResult, TestSuiteResult,
)
from planner import parse_yaml


# ── 离线测试 ──

def test_data_models():
    """测试 suite 数据模型"""
    # ActionStep
    a = ActionStep(description="打开设置", timeout=10)
    assert a.description == "打开设置"

    # AssertStep
    s = AssertStep(expectation="看到 Logo", severity="warning", retry_on_fail=True)
    assert s.retry_on_fail is True

    # TestCase
    case = TestCase(name="test", steps=[a, s], continue_on_error=True)
    assert len(case.steps) == 2

    # Timing
    t = Timing.start_now()
    time.sleep(0.01)
    t.stop()
    assert t.duration_ms > 0

    # StepResult
    sr = StepResult(step=a, success=True, timing=t)
    assert sr.success

    # TestCaseResult
    cr = TestCaseResult(case_name="test", steps=[sr], status="passed")
    assert cr.passed_count == 1

    # TestSuiteResult
    suite_r = TestSuiteResult(suite_name="suite", cases=[cr])
    assert suite_r.total == 1 and suite_r.passed == 1 and suite_r.failed == 0

    print("✓ 数据模型测试通过\n")


def test_yaml_parsing():
    """测试 YAML 解析"""
    yaml_path = os.path.join(os.path.dirname(__file__), "..", "examples", "toutiao_comment.yaml")
    if not os.path.exists(yaml_path):
        print("⏭ 未找到示例 YAML，跳过\n")
        return

    # 设置假环境变量避免解析报错
    env_backup = {}
    for key in ["AUTOGLM_BASE_URL", "AUTOGLM_API_KEY", "GEMINI_API_KEY"]:
        env_backup[key] = os.environ.get(key)
        if key not in os.environ:
            os.environ[key] = "test-placeholder"

    try:
        suite, device_cfg, autoglm_cfg, vlm_cfg = parse_yaml(yaml_path)

        assert suite.name == "今日头条评论区红包横幅测试"
        assert device_cfg.device_type == "adb"
        assert len(suite.test_cases) == 1

        case = suite.test_cases[0]
        assert len(case.steps) == 4
        assert isinstance(case.steps[0], ActionStep)
        assert isinstance(case.steps[3], AssertStep)
        assert case.steps[3].retry_on_fail is True

        print(f"  suite: {suite.name}")
        print(f"  steps: {len(case.steps)}")
        print(f"  vlm: {vlm_cfg.provider}/{vlm_cfg.model}")
        print("✓ YAML 解析测试通过\n")
    finally:
        for key, val in env_backup.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val


def test_env_var_resolution():
    """测试 YAML 中的环境变量解析"""
    os.environ["TEST_AUTOQA_KEY"] = "my-secret-123"

    import yaml
    import tempfile
    yaml_content = """
name: env test
config:
  autoglm:
    api_key: "${TEST_AUTOQA_KEY}"
    base_url: "http://localhost"
  vlm:
    provider: "gemini"
    api_key: "${TEST_AUTOQA_KEY}"
tasks:
  - name: test
    flow:
      - action: "test action"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmp_path = f.name

    try:
        _, _, autoglm_cfg, vlm_cfg = parse_yaml(tmp_path)
        assert autoglm_cfg.api_key == "my-secret-123"
        assert vlm_cfg.api_key == "my-secret-123"
        print("✓ 环境变量解析测试通过\n")
    finally:
        os.remove(tmp_path)
        del os.environ["TEST_AUTOQA_KEY"]


if __name__ == "__main__":
    print("=" * 50)
    print("Phase 4 编排串联验证")
    print("=" * 50)

    print("\n── 离线测试 ──\n")
    test_data_models()
    test_yaml_parsing()
    test_env_var_resolution()

    print("── 端到端测试 ──\n")
    print("请使用以下命令运行端到端测试:")
    print("  python main.py run examples/toutiao_comment.yaml -v")
    print()

    print("=" * 50)
    print("Phase 4 离线验证完成!")