# AutoQA

基于 AutoGLM + VLM 的移动端自动化测试框架。

采用双模型架构：**AutoGLM** 负责手机操作（点击、滑动、输入），**VLM**（视觉语言模型）负责截图断言，实现"操作"与"验证"的分离。

## 环境准备

### 1. 安装依赖

```bash
# Python >= 3.10
pip install -e .
```

这会自动安装所有依赖，包括 [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM)。

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入你的 API Key：

```bash
cp .env.example .env
```

```env
# Gemini（视觉断言 + 规划）
GEMINI_API_KEY=your-gemini-api-key

# AutoGLM（手机操作）— 智谱 BigModel API
AUTOGLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
AUTOGLM_API_KEY=your-autoglm-api-key
```

运行前加载环境变量：

```bash
export $(grep -v '^#' .env | xargs)
```

### 3. 配置 ADB（Android）

#### 安装 ADB

```bash
# macOS
brew install android-platform-tools

# Ubuntu / Debian
sudo apt install adb

# Windows
# 下载 SDK Platform Tools：https://developer.android.com/tools/releases/platform-tools
# 解压后将目录添加到系统 PATH
```

#### 手机端设置

1. 进入 **设置 → 关于手机**，连续点击「版本号」7 次，开启开发者模式
2. 进入 **设置 → 开发者选项**，开启：
   - **USB 调试**
   - **USB 调试（安全设置）**（部分手机需要，允许通过 ADB 模拟点击）
3. 用 USB 数据线连接手机和电脑
4. 手机上弹出「允许 USB 调试」对话框，勾选「始终允许」并确认

#### 验证连接

```bash
adb devices
```

正常输出：

```
List of devices attached
XXXXXXXX    device
```

> 如果显示 `unauthorized`，请在手机上确认 USB 调试授权弹窗。
> 如果显示 `offline`，尝试拔插 USB 或 `adb kill-server && adb start-server`。

#### 安装 ADB Keyboard（必需）

AutoQA 通过 [ADB Keyboard](https://github.com/nicnocquee/AdbKeyboard) 实现中文输入，需要在手机上安装：

```bash
# 下载 APK
wget https://github.com/nicnocquee/AdbKeyboard/releases/download/v2.0.0/AdbKeyboard.apk

# 安装到手机
adb install AdbKeyboard.apk
```

安装后在手机上启用：**设置 → 语言和输入法 → ADB Keyboard** → 开启。

> 框架会在输入文字时自动切换到 ADB Keyboard，输入完成后自动恢复原始输入法。

#### HarmonyOS 设备

HarmonyOS 使用 HDC 工具替代 ADB：

```bash
hdc list targets   # 列出设备
```

## 使用方式

AutoQA 提供三种运行模式：

### 模式 1：执行 YAML 测试用例

编写 YAML 测试用例，直接执行：

```bash
python main.py run examples/toutiao_comment.yaml -v
```

YAML 格式示例：

```yaml
name: 评论区横幅测试

device:
  type: android

config:
  autoglm:
    base_url: "${AUTOGLM_BASE_URL}"
    api_key: "${AUTOGLM_API_KEY}"
  vlm:
    provider: "gemini"
    api_key: "${GEMINI_API_KEY}"
    model: "gemini-2.5-flash"

tasks:
  - name: 横幅验证
    flow:
      - action: "打开今日头条 App"
        timeout: 15
      - action: "点击推荐页面中的第一篇文章"
      - action: "点击评论图标进入评论区"
      - assert: "评论区顶部出现了一个红色横幅"
        severity: critical
```

### 模式 2：自然语言生成 YAML

用自然语言描述测试场景，LLM 自动分解为操作步骤和断言，生成 YAML 文件：

```bash
# 输出到文件
python main.py generate "打开微信，进入朋友圈，检查第一条是否有点赞按钮" -o examples/wechat.yaml

# 输出到终端预览
python main.py generate "打开设置，检查 WiFi 是否已开启"
```

生成后可通过 `run` 模式执行。

### 模式 3：交互式测试

进入交互模式，输入自然语言 → 自动规划 → 确认后执行 → 循环：

```bash
python main.py interactive --device-type adb
```

```
请描述测试场景: 打开今日头条，找到一篇文章，检查评论区是否有横幅

规划中...

  用例: 今日头条评论区横幅检查
  步骤:
    1. [操作] 打开今日头条App
    2. [操作] 点击推荐页面中的第一篇文章
    3. [操作] 点击评论图标进入评论区
    4. [断言] 评论区顶部显示横幅

是否执行? (Y/n): y
```

## CLI 参数

```
python main.py run <yaml_path> [--device-type adb|hdc|ios] [--device-id ID] [-v]
python main.py generate <description> [-o OUTPUT] [--device-type android|harmony|ios] [-v]
python main.py interactive [--device-type adb|hdc|ios] [--device-id ID] [-v]
```

| 参数 | 说明 |
|---|---|
| `--device-type` | 设备类型，默认 adb（Android） |
| `--device-id` | 指定设备 ID，不指定则自动检测 |
| `-v, --verbose` | 输出详细调试日志 |
| `-o, --output` | generate 模式的输出文件路径 |

## 项目结构

```
├── main.py              # CLI 入口
├── config/              # 配置数据类（VLM、AutoGLM、Planner、Device）
├── planner/             # YAML 解析 + LLM 规划器
├── executor/            # AutoGLM 执行器
├── asserter/            # VLM 视觉断言
├── providers/           # 统一模型 Provider 层（Gemini / OpenAI 兼容）
├── screenshot/          # 截图管理
├── runner.py            # 测试编排与容错重试
├── suite.py             # 数据模型（TestCase、TestSuite 等）
├── examples/            # 示例 YAML 用例
└── tests/               # 测试脚本
```