# PocketPledge

<div align="center">
  <img src="imgs/logo.jpg" alt="PocketPledge Logo" width="200" />
</div>

<div align="center">
  <strong>PocketPledge</strong> 是一个面向学习监督场景的硬核 AI 陪伴与监督系统。<br>
  结合 <b>Live2D 虚拟形象</b>、<b>实时语音对话</b>、<b>视觉状态分析</b> 和 <b>经济惩罚机制</b>，为你打造全方位的沉浸式学习体验。<br>
  <i>用真金白银的代价，终结你的分心时刻！</i>
</div>

---

## 🌟 核心魅力与特色

PocketPledge 打破了传统时间管理软件的枯燥与死板，将“陪伴”与“督导”完美融合：

- 🎭 **Live2D 虚拟伙伴**：告别冷冰冰的倒计时器！系统提供互动式的虚拟伙伴前端界面，支持表情与动作同步，全程陪你一起度过漫长的学习时光。
- 🗣️ **极速实时语音对话**：通过强大的本地 ASR (Sherpa-ONNX) 与云端 TTS 的组合，加上代理模型的思考，实现极低延迟的语音流转。想开小差？你的伙伴不仅会用语音提醒你，还会给予你灵魂的拷问。
- 👁️ **硬核视觉分心判定**：学习时频繁看手机、离开座位？系统会定时进行摄像头抽帧，由强大的多模态 AI (如 GPT-4o) 进行**实时状态分析**，闭环扣费逻辑，精准捕捉你的每一次分心。
- 💰 **经济督导 (真金白银的考验)**：开启专注前需“预扣押金”。一旦被 AI 抓到分心，将立即扣除一定罚金，仅在专注结束后退还剩余金额。真实的余额结算机制，用痛感建立起最坚固的专注力防线。

## 📁 目录结构与技术栈概览

本项目采用前后端分离架构，追求极致的开发体验与运行效率：

- **前端 (`frontend/`)**：React + TypeScript + Vite, Tailwind CSS v4 (无 `tailwind.config.js` 纯 `@theme` 驱动), Zustand 状态管理。负责聊天 UI、Live2D 展示、录音采集与 WebSocket 通信。
- **后端 (`backend/`)**：FastAPI + Python 3.12, SQLAlchemy。负责核心业务（钱包、惩罚结算）、WebSocket 网关路由、本地 ASR 推理及 TTS 转发。彻底拥抱 `uv` 极速包管理与运行。
- **文档 (`docs/`)**：REST API 标准与 WebSocket 协议文档。

---

## 🚀 快速开始与安装指南

**重要提示：本项目重度依赖本地 ASR 模型（Sherpa-ONNX），请务必按照下方指南完整下载并放置模型文件。**

### 0. 环境前置要求

- **Node.js**: `v20+` 并且严格使用 `pnpm` (`npm` 和 `yarn` 在本项目中被禁止)。
- **Python**: `3.12+` (推荐使用 `uv` 进行环境和包管理)。

### 1. 准备本地 ASR 模型 (Sherpa-ONNX SenseVoice)

为了实现极低延迟的语音交互，麦克风音频流会通过 WebSocket 实时发送给后端进行本地 ASR 转写。

1. **下载模型**：
   前往 Sherpa-ONNX 官方资源库或 HuggingFace 获取对应的模型包 (`sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`)。
2. **确认文件就绪**：
   解压后，请确保包内包含以下关键文件，并记录其**绝对路径**：
   - `model.int8.onnx`
   - `tokens.txt`

### 2. 后端配置与启动 (Backend)

进入后端目录并使用 `uv` 进行环境安装与管理：

```bash
cd backend
# 使用 uv 安装依赖
uv pip install -r requirements.txt
```

**配置环境变量 (`backend/.env`)**：

在 `backend` 目录下复制 `.env.example` 并命名为 `.env`，然后填入你的真实配置：

```env
# 开启本地代理模型架构
AGENT_BACKEND=local

# ----------------- ASR 模型路径 -----------------
# (严格替换为你本地解压后的真实绝对路径)
MEDIA_AI_SHERPA_MODEL_PATH="/绝对路径/sherpa-onnx/model.int8.onnx"
MEDIA_AI_SHERPA_TOKENS_PATH="/绝对路径/sherpa-onnx/tokens.txt"

# ----------------- AI 模型配置 -----------------
# 聊天模型配置
LOCAL_CHAT_API_KEY="sk-你的聊天模型API-KEY"
LOCAL_CHAT_API_BASE="https://api.openai.com/v1"
LOCAL_CHAT_MODEL="gpt-4o"
LOCAL_CHAT_TEMPERATURE=0.55

# 视觉模型配置 (用于判定是否分心)
LOCAL_VISION_API_KEY="sk-你的视觉模型API-KEY"
LOCAL_VISION_API_BASE="https://api.openai.com/v1"
LOCAL_VISION_MODEL="gpt-4o"

# 系统智能体配置
LOCAL_AGENT_API_KEY="sk-你的系统代理API-KEY"
LOCAL_AGENT_API_BASE="https://api.openai.com/v1"
LOCAL_AGENT_MODEL="gpt-4o"
LOCAL_AGENT_TEMPERATURE=0.1
```

**启动后端服务**：
```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 12393 --reload
```
*提示：初次启动会自动在 `backend/reward.db` 初始化数据库并创建必要的预设账户。*

**后端补充配置表** (可在 `.env` 覆盖默认行为)：

| 变量名 | 说明 | 默认值 |
|---|---|---|
| `DATABASE_URL` | 数据库文件路径 | `sqlite:///./reward.db` |
| `AUTH_SECRET_KEY` | 鉴权 JWT 的 Secret | 仅重启单次随机生成 |
| `MEDIA_AI_TTS_PROVIDER` | 语音合成服务商 | `qwen-realtime` |
| `MEDIA_AI_SHERPA_MODEL_TYPE` | 本地 ASR 模型类型 | `sense_voice` |

*注：如果 ASR 路径配置错误或找不到文件，系统在运行时不会出错崩溃，但用户的每一次语音输入均将回落为空白文本。*

### 3. 前端配置与启动 (Frontend)

请确保你已经安装了 `pnpm`。

```bash
cd frontend
# 安装依赖
pnpm install

# 启动开发服务器
pnpm run dev
```
启动完毕后，在浏览器中打开相应的本地地址 (默认 `http://localhost:5173/`)。前端会自动通过 WebSocket 连接到 `ws://localhost:12393/ws`。

> **快捷启动提示 (双端联合启动，推荐 Windows 用户)**：
> 在所有依赖和环境配置就绪后，你可以直接在项目根目录运行 `.\start-dev.cmd`，脚本会自动为你唤起双端的控制台进行联合启动。

---

## 💻 开发者指南

我们非常欢迎开发者参与贡献，在提交代码前，请确保遵循以下代码规范和测试要求：

### 前端开发指令
- **代码规范检查**：`pnpm run lint` (在提交 PR 前务必确保无报错)
- **运行 Mock 服务器**：`pnpm run mock` (用于脱离后端独立测试前端 UI)
- **构建生产包**：`pnpm run build`

### 后端开发指令
- **代码格式化与 Lint**：我们使用 `ruff` 作为唯一的格式化和静态分析工具：
  ```bash
  cd backend
  uv run ruff check .
  uv run ruff format .
  ```
- **运行单元测试**：使用 `pytest` 运行所有测试：
  ```bash
  cd backend
  PYTHONPATH=. uv run pytest
  ```

---

## 📚 详细文档与资料

想要深入了解 PocketPledge 的内部机制与协议，请参阅以下文档：

- 📄 **接口文档**: [docs/api_contract.md](docs/api_contract.md)
- 🔌 **协议说明**: [docs/ws_protocol.md](docs/ws_protocol.md)

> *“一旦你许下承诺 (Pledge)，就请专注于当下。”*
