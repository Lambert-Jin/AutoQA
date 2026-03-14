"""Phase 1 验证脚本：测试 VLM Provider 能否接收截图并返回文本响应"""

import base64
import os

from config.settings import VLMConfig
from asserter.vlm_providers import create_vlm_provider


def test_gemini():
    """测试 GeminiProvider"""
    config = VLMConfig(
        provider="gemini",
        api_key=os.environ["GEMINI_API_KEY"],
        model="gemini-3-pro-image-preview",
    )
    provider = create_vlm_provider(config)

    img_b64 = _load_test_image()

    result = provider.chat(
        system_prompt='判断截图中的内容，回复 JSON: {"description": "简短描述"}',
        image_base64=img_b64,
        user_prompt="请描述这张截图的主要内容",
    )
    print(f"[Gemini] 响应:\n{result}")
    assert len(result) > 0, "Gemini 返回为空"
    print("✓ Gemini Provider 测试通过\n")


def test_qwen():
    """测试 QwenVLProvider"""
    config = VLMConfig(
        provider="qwen",
        base_url=os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        api_key=os.environ["QWEN_API_KEY"],
        model=os.environ.get("QWEN_MODEL", "qwen-vl-max"),
    )
    provider = create_vlm_provider(config)

    img_b64 = _load_test_image()

    result = provider.chat(
        system_prompt='判断截图中的内容，回复 JSON: {"description": "简短描述"}',
        image_base64=img_b64,
        user_prompt="请描述这张截图的主要内容",
    )
    print(f"[Qwen] 响应:\n{result}")
    assert len(result) > 0, "Qwen 返回为空"
    print("✓ Qwen Provider 测试通过\n")


def _load_test_image() -> str:
    """加载测试图片，优先用本地文件，否则生成一张纯色小图"""
    test_paths = [
        "test_screenshot.png", "test_screenshot.jpg", "test_screenshot.jpeg",
        "tests/test_screenshot.png", "tests/test_screenshot.jpg", "tests/test_screenshot.jpeg",
    ]
    for path in test_paths:
        if os.path.exists(path):
            with open(path, "rb") as f:
                print(f"使用测试图片: {path}")
                return base64.b64encode(f.read()).decode()

    # 没有测试图片，生成一张 100x100 的简单 PNG
    print("未找到测试图片，生成占位图...")
    import struct
    import zlib

    width, height = 100, 100
    raw_data = b""
    for _ in range(height):
        raw_data += b"\x00" + b"\x41\x82\xc3" * width  # filter byte + RGB

    def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += _png_chunk(b"IDAT", zlib.compress(raw_data))
    png += _png_chunk(b"IEND", b"")
    return base64.b64encode(png).decode()


if __name__ == "__main__":
    print("=" * 50)
    print("Phase 1 VLM Provider 验证")
    print("=" * 50)

    has_gemini = "GEMINI_API_KEY" in os.environ
    has_qwen = "QWEN_API_KEY" in os.environ

    if not has_gemini and not has_qwen:
        print("请设置至少一个环境变量: GEMINI_API_KEY 或 QWEN_API_KEY")
        exit(1)

    if has_gemini:
        test_gemini()
    else:
        print("⏭ 跳过 Gemini（未设置 GEMINI_API_KEY）\n")

    if has_qwen:
        test_qwen()
    else:
        print("⏭ 跳过 Qwen（未设置 QWEN_API_KEY）\n")

    print("=" * 50)
    print("Phase 1 验证完成!")