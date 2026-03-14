# AutoQA 对话上下文传递

> 本文件用于将当前对话的完整上下文传递给新对话。新对话开始时请先阅读本文件和 `AutoQA-ARCHITECTURE.md`。

## 1. 项目背景

用户在 `/Users/bytedance/ai/agent/` 下学习两个开源 AI Agent 项目，并基于所学设计自己的测试框架。

### 已完成的分析

| 项目 | 路径 | 产出文档 |
|------|------|----------|
| Midscene.js | `midscene/` | `midscene/ARCHITECTURE.md`、`midscene/ARCHITECTURE-AUTOGLM.md` |
| Open-AutoGLM | `Open-AutoGLM/` | `Open-AutoGLM/ARCHITECTURE.md` |

### 关键发现（影响后续设计）

- **Midscene 对 AutoGLM 的使用方式**：只用 AutoGLM 作为"大脑"获取操作指令，通过 `transformAutoGLMAction()` 转换为 Midscene 自己的 `PlanningAction` 格式，再通过 `AbstractInterface` 执行。AutoGLM 对设备没有直接控制权。
- **Open-AutoGLM 的接口封装**：三层接口——`PhoneAgent`（顶层 Agent 循环）、`ModelClient` / `ActionHandler`（中层）、`DeviceFactory`（底层设备操作）。

## 2. AutoQA 框架设计

### 目标

用自然语言描述测试流程和预期结果，框架自动操作手机并用视觉模型做断言。

**示例：**
```
打开今日头条，点击一个文章，点击评论区。
预期：评论区顶部会出现一个发评论得红包的横幅。
```

### 架构文档

**`AutoQA-ARCHITECTURE.md`**（16 个章节，~1900 行）

包含：分层架构、目录结构、核心执行流程、YAML DSL、数据模型、所有关键模块的代码设计、容错机制、报告系统、实施计划等。

## 3. 经过多轮讨论确定的核心设计决策

### 决策 1：双模型分离

- **AutoGLM** — 负责操作手机（tap/swipe/type），通过 OpenAI 兼容 API 调用
- **VLM（可配置）** — 负责视觉断言，支持 Qwen3-VL 和 Gemini 2.5 Pro
- 所有模型均通过远程 API 调用，不依赖本地部署

### 决策 2：复用 Open-AutoGLM 中底层组件，不用 PhoneAgent 顶层接口

**原因：**

- `PhoneAgent.run()` — 一次跑完整个任务，无法中途插入断言
- `PhoneAgent.step()` — 只在第一轮（`context` 为空时）传入任务描述，后续轮次的 `user_prompt` 被丢弃：
  ```python
  # agent.py _execute_step():
  if is_first:
      text = f"{user_prompt}\n\n{screen_info}"    # ← 带任务描述
  else:
      text = f"** Screen Info **\n\n{screen_info}" # ← 丢弃 user_prompt
  ```
  多步串联时，不 reset 则新指令传不进去，reset 则丢失上下文。

**复用清单：**

| 组件 | 来源 | 用途 |
|------|------|------|
| `ModelClient` | `phone_agent.model.client` | AutoGLM API 调用 |
| `ModelConfig` | `phone_agent.model.client` | 模型配置 |
| `MessageBuilder` | `phone_agent.model.client` | 消息构建、图片移除 |
| `ActionHandler` | `phone_agent.actions.handler` | 动作执行、坐标转换 |
| `parse_action` | `phone_agent.actions.handler` | AST 动作解析 |
| `DeviceFactory` | `phone_agent.device_factory` | 设备操作（ADB/HDC/iOS） |
| `get_system_prompt` | `phone_agent.config` | AutoGLM 系统提示词 |

### 决策 3：TestExecutor — 自管理对话上下文

核心创新：不用 PhoneAgent，而是复用其内部组件，自己控制 `_context` 列表。

- **整个 TestCase 共享 `_context`**（不每步 reset）：AutoGLM 有完整操作历史，更好地理解当前状态
- **每个新 ActionStep 都能注入新任务描述**到已有上下文（解决了 `step()` 的限制）
- **`handle_unexpected("关闭弹窗")`**：向已有上下文注入清理指令，让 AutoGLM 处理干扰
- **每个 TestCase 开始时 `reset()`**：不同用例间互不干扰

### 决策 4：三级容错机制

| 层级 | 机制 | 处理什么 |
|------|------|----------|
| Level 1 | ActionStep 内部 AutoGLM 多轮循环 | 操作过程中弹窗——AutoGLM 看到截图自然处理 |
| Level 2 | AssertStep 失败 → `handle_unexpected()` → 重新断言 | 断言时屏幕被弹窗遮挡 |
| Level 3 | TestCase 级 `continueOnError` | 某步骤彻底失败——跳过继续后续 |

### 决策 5：VLM 可插拔

- `VLMProvider` 协议：`chat(system_prompt, image_base64, user_prompt) -> str`
- `QwenVLProvider`：OpenAI 兼容 API（DashScope），用 `openai` SDK
- `GeminiProvider`：Google GenAI SDK，图片用 `Part.from_bytes()`
- `create_vlm_provider(config)` 工厂函数根据 `config.provider` 字段创建实例
- 扩展新 VLM 只需实现 `chat` 方法并注册到工厂

### 决策 6：YAML 优先，自然语言可选

```yaml
config:
  autoglm:
    base_url: "http://localhost:8000/v1"
    api_key: "${AUTOGLM_API_KEY}"
    model: "autoglm-phone-9b"
  vlm:
    provider: "qwen"       # qwen | gemini
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: "${DASHSCOPE_API_KEY}"
    model: "qwen-vl-max"

tasks:
  - name: 测试名
    flow:
      - action: "打开今日头条 App"
      - action: "点击第一篇文章"
      - assert: "评论区顶部有红包横幅"
        severity: critical
        retryOnFail: true
        retryCleanup: "关闭弹窗或广告"
```

## 4. 实施计划（6 个阶段）

```
Phase 1 ██████░░░░░░░░░░░░░░░░░░░░░░  项目骨架 + VLM Provider
Phase 2 ░░░░░░████░░░░░░░░░░░░░░░░░░  断言能力 (Asserter)
Phase 3 ░░░░░░████░░░░░░░░░░░░░░░░░░  执行能力 (TestExecutor)  ← 与 Phase 2 可并行
Phase 4 ░░░░░░░░░░████████░░░░░░░░░░  编排串联 (Runner+YAML+CLI) ← 第一个可交付版本
Phase 5 ░░░░░░░░░░░░░░░░░░█████░░░░░  测试报告 (HTML)
Phase 6 ░░░░░░░░░░░░░░░░░░░░░░░█████  增强功能 (按需)
```

### Phase 1：项目骨架 + VLM Provider
- `config/settings.py` — VLMConfig, AutoGLMConfig 数据类
- `asserter/vlm_providers/__init__.py` — VLMProvider 协议 + 工厂
- `asserter/vlm_providers/qwen.py` — QwenVLProvider
- `asserter/vlm_providers/gemini.py` — GeminiProvider
- 验证：两个 Provider 能接收截图返回文本响应

### Phase 2：断言能力
- `asserter/asserter.py` — Asserter 核心（调 VLMProvider → 解析 JSON → AssertResult）
- `asserter/prompts.py` — 断言提示词模板
- `screenshot/manager.py` — ScreenshotManager
- 验证：对真实设备截图做视觉断言，输出 pass/fail + reason + confidence

### Phase 3：执行能力（与 Phase 2 可并行）
- `executor/executor.py` — TestExecutor（自管理上下文、execute_action、handle_unexpected、reset）
- 验证：连续多步操作保持上下文，弹窗能处理

### Phase 4：编排串联（第一个可交付版本）
- `suite.py` — TestSuite, TestCase, ActionStep, AssertStep 等数据模型
- `planner/parser.py` — YAML 解析器
- `runner.py` — TestRunner（编排 + 容错重试）
- `main.py` — CLI 入口
- 验证：`python main.py run examples/toutiao_comment.yaml` 端到端跑通

### Phase 5：测试报告
- `report/generator.py` — ReportGenerator（inline/directory 两种模式）
- `report/template.html` — Jinja2 HTML 模板
- 验证：生成 HTML 报告，含截图和 VLM 推理过程

### Phase 6：增强功能（按需）
- continueOnError、waitFor 轮询断言、Planner（自然语言→YAML）、JUnit XML、iOS 支持

## 5. 目录结构

```
auto-qa/
├── auto_qa/
│   ├── __init__.py
│   ├── runner.py                  # TestRunner
│   ├── suite.py                   # 数据模型
│   ├── executor/
│   │   └── executor.py            # TestExecutor
│   ├── asserter/
│   │   ├── asserter.py            # Asserter
│   │   ├── prompts.py             # 断言提示词
│   │   └── vlm_providers/
│   │       ├── __init__.py        # VLMProvider 协议 + 工厂
│   │       ├── qwen.py            # QwenVLProvider
│   │       └── gemini.py          # GeminiProvider
│   ├── planner/
│   │   └── parser.py              # YAML 解析器
│   ├── report/
│   │   ├── generator.py           # ReportGenerator
│   │   └── template.html          # HTML 模板
│   ├── screenshot/
│   │   └── manager.py             # ScreenshotManager
│   └── config/
│       └── settings.py            # 全局配置
├── phone_agent/                   # ← 直接引用 Open-AutoGLM
├── examples/
│   └── toutiao_comment.yaml
└── main.py                        # CLI 入口
```