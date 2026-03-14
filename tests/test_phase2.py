"""Phase 2 验证脚本：测试 Asserter 断言能力 + ScreenshotManager"""

import base64
import os

from asserter import Asserter
from config.settings import AssertResult, Screenshot, VLMConfig
from screenshot import ScreenshotManager


# ── 1. 离线测试：不需要 API key ──

def test_data_models():
    """测试 Screenshot 和 AssertResult 数据类"""
    s = Screenshot(base64="dGVzdA==")
    assert s.id, "id 应自动生成"
    assert s.timestamp > 0, "timestamp 应自动设置"
    print(f"  Screenshot: id={s.id}, ts={s.timestamp:.0f}")

    r = AssertResult(passed=True, reason="test", confidence=0.95)
    assert r.retried is False
    print(f"  AssertResult: passed={r.passed}, retried={r.retried}")
    print("✓ 数据模型测试通过\n")


def test_parse_response():
    """测试 Asserter 的 JSON 解析逻辑"""
    asserter = object.__new__(Asserter)
    asserter.provider = None

    # 正常 JSON
    r1 = asserter._parse_response('{"passed": true, "reason": "看到了按钮", "confidence": 0.9}')
    assert r1.passed is True and r1.confidence == 0.9
    print("  正常 JSON: OK")

    # markdown ```json ``` 包裹
    r2 = asserter._parse_response('```json\n{"passed": false, "reason": "没有横幅", "confidence": 0.8}\n```')
    assert r2.passed is False and r2.confidence == 0.8
    print("  markdown 包裹: OK")

    # 解析失败兜底
    r3 = asserter._parse_response("这不是JSON啊")
    assert r3.passed is False and r3.confidence == 0.0
    print("  解析失败兜底: OK")

    print("✓ JSON 解析测试通过\n")


def test_screenshot_manager():
    """测试 ScreenshotManager 加载本地图片"""
    mgr = ScreenshotManager()

    test_paths = [
        "test_screenshot.png", "test_screenshot.jpg", "test_screenshot.jpeg",
        "tests/test_screenshot.png", "tests/test_screenshot.jpg", "tests/test_screenshot.jpeg",
    ]
    found = None
    for path in test_paths:
        if os.path.exists(path):
            found = path
            break

    if not found:
        print("⏭ 未找到测试图片，跳过 ScreenshotManager 测试\n")
        return

    ss = mgr.from_file(found)
    assert ss.base64, "base64 不应为空"
    assert ss.id, "id 应自动生成"
    print(f"  from_file({found}): {ss.width}x{ss.height}, id={ss.id}")

    # 测试保存
    save_path = "tests/test_output.png"
    mgr.save(ss, save_path)
    assert os.path.exists(save_path)
    print(f"  save → {save_path}: OK")
    os.remove(save_path)

    print("✓ ScreenshotManager 测试通过\n")


# ── 2. 在线测试：需要 API key + 测试截图 ──

def test_asserter_gemini():
    """用 Gemini 对真实截图做视觉断言"""
    config = VLMConfig(
        provider="gemini",
        api_key=os.environ["GEMINI_API_KEY"],
        model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    )
    _run_asserter_test(config, "Gemini")


def test_asserter_qwen():
    """用 Qwen 对真实截图做视觉断言"""
    config = VLMConfig(
        provider="qwen",
        base_url=os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        api_key=os.environ["QWEN_API_KEY"],
        model=os.environ.get("QWEN_MODEL", "qwen-vl-max"),
    )
    _run_asserter_test(config, "Qwen")


def _run_asserter_test(config: VLMConfig, name: str):
    """通用断言测试：一个应该通过、一个应该失败"""
    mgr = ScreenshotManager()
    screenshot = _load_screenshot(mgr)
    if screenshot is None:
        print(f"⏭ 无测试截图，跳过 {name} Asserter 在线测试\n")
        return

    asserter = Asserter(config)

    # 测试 1: 应该通过的断言（截图中大概率存在的内容）
    r1 = asserter.verify(screenshot, "截图中评论区上方有一个背景是白色的横幅，横幅上的文本是一个话题，横幅右边有一个红色按钮，按钮上面的文本是去发布")
    print(f"  [{name}] 断言'有文字或图标': passed={r1.passed}, confidence={r1.confidence:.2f}")
    print(f"         reason: {r1.reason}")

    # 测试 2: 应该失败的断言
    r2 = asserter.verify(screenshot, "截图中有一只恐龙在跳舞")
    print(f"  [{name}] 断言'恐龙跳舞': passed={r2.passed}, confidence={r2.confidence:.2f}")
    print(f"         reason: {r2.reason}")

    assert r1.passed != r2.passed, f"两个断言结果不应相同（都是 {r1.passed}）"
    print(f"✓ {name} Asserter 在线测试通过\n")


def _load_screenshot(mgr: ScreenshotManager) -> Screenshot | None:
    test_paths = [
        "test_screenshot.png", "test_screenshot.jpg", "test_screenshot.jpeg",
        "tests/test_screenshot.png", "tests/test_screenshot.jpg", "tests/test_screenshot.jpeg",
    ]
    for path in test_paths:
        if os.path.exists(path):
            print(f"  使用测试图片: {path}")
            return mgr.from_file(path)
    return None


if __name__ == "__main__":
    print("=" * 50)
    print("Phase 2 断言能力验证")
    print("=" * 50)

    # 离线测试（始终运行）
    print("\n── 离线测试 ──\n")
    test_data_models()
    test_parse_response()
    test_screenshot_manager()

    # 在线测试（需要 API key）
    has_gemini = "GEMINI_API_KEY" in os.environ
    has_qwen = "QWEN_API_KEY" in os.environ

    if has_gemini or has_qwen:
        print("── 在线测试 ──\n")
        if has_gemini:
            test_asserter_gemini()
        else:
            print("⏭ 跳过 Gemini（未设置 GEMINI_API_KEY）\n")

        if has_qwen:
            test_asserter_qwen()
        else:
            print("⏭ 跳过 Qwen（未设置 QWEN_API_KEY）\n")
    else:
        print("── 跳过在线测试（未设置 GEMINI_API_KEY 或 QWEN_API_KEY）──\n")

    print("=" * 50)
    print("Phase 2 验证完成!")