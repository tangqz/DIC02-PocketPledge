# PocketPledge

![logo](imgs/logo.jpg)

**PocketPledge** 是一个面向学习监督场景的 AI 陪伴系统。通过结合 Live2D 虚拟形象、实时语音对话与摄像头视觉监督，系统能够在用户学习过程中提供陪伴、监督，并引入经济惩罚机制来避免分心。

##  项目概述

核心机制：用户通过预扣押金开始专注会话，系统在后台定时通过摄像头抽帧进行**视觉注意力实时判定**。如果检测到用户玩手机或离开座位，系统将扣除一定罚金，并在结束后退还剩余押金。整个过程由 AI 虚拟伙伴进行语音和文字的双重引导与监督。

### 核心特性
-  **Live2D 虚拟陪伴**：互动式前端界面，支持表情与动作同步。
-  **实时语音流转**：前端录音 -> Sherpa-ONNX 本地 VAD/ASR 识别 -> LLM 思考 -> TTS 语音流式下发。
-  **视觉分心判定**：调用 Dify 视觉工作流，动态分析用户当前状态，实时闭环扣费逻辑。
-  **经济督导模型**：真实的余额扣除与结算机制，强化监督效果。

##  目录结构

- frontend/：React + TypeScript + Vite 前端，负责聊天 UI、Live2D 展示、录音采集与 WebSocket 通信。
- backend/：FastAPI 后端，负责核心业务（钱包、惩罚结算）、WebSocket 网关路由、本地 ASR 推理及 TTS 转发。
- dify_orchestration/：Dify 编排配置，包含聊天、视觉判定、系统代理工作流的 YAML 导出与 Persona 设定。
- docs/：REST API 标准与 WebSocket 协议文档。

---

##  快速开始与环境配置

 **重要提示：本项目重度依赖本地 ASR 模型（Sherpa-ONNX），请务必按照下方指南完整下载并放置模型文件。**

### 1. 准备本地 ASR 模型 (Sherpa-ONNX SenseVoice)

由于我们需要极低延迟的语音交互，麦克风流数据会通过 WebSocket 发送给后端进行本地 ASR 转写。

1. **下载模型**：
   前往 Sherpa-ONNX 官方资源库或 HuggingFace 获取对应的模型包(sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17)。
2. **确认文件就绪**：
   解压后，请确保包内包含以下关键文件，并记录你的绝对路径（后续要配置到环境变量中）：
   - model.int8.onnx
   - 	okens.txt

### 2. 后端配置与启动 (Backend)

**环境要求**：Python 3.10+ (推荐使用 Conda)

`bash
cd backend
pip install -r requirements.txt
`

**配置环境变量**：
在 backend/.env 或项目根目录新建 .env 文件。提供大模型 API 密钥以及刚才准备的 ASR 模型路径：

`ini
# --- ASR 模型路径 (严格替换为你本地包含以上两个文件的真实绝对路径) ---
MEDIA_AI_SHERPA_MODEL_PATH="C:/Users/YourName/path/to/sherpa-onnx/model.int8.onnx"
MEDIA_AI_SHERPA_TOKENS_PATH="C:/Users/YourName/path/to/sherpa-onnx/tokens.txt"

# --- 大模型与 TTS (DashScope 用于 Qwen 本地代理与流式语音合成) ---
DASHSCOPE_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"

# （可选）连接真实的 Dify 工作流
# MEDIA_AI_USE_REAL_DIFY=1
# DIFY_API_BASE="http://your-dify-ip/v1"
# DIFY_CHAT_API_KEY="app-xxx"
# DIFY_VISION_API_KEY="app-xxx"
# DIFY_SYSTEM_AGENT_API_KEY="app-xxx"
`

**启动后端**：
`bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 12393 --reload
`
*启动后会自动在 backend/reward.db 初始化数据库和预设账户。*

### 3. 前端配置与启动 (Frontend)

**环境要求**：Node.js 20+, npm 10+

`bash
cd frontend
npm install
npm run dev
`
启动完毕后浏览器打开相应本地地址即可，前端默认会连接上 ws://localhost:12393/ws。

###  双端联合启动（Windows 推荐）
依赖就绪后，直接在根目录执行脚本，自动弹出双控制台。

---

##  后端补充配置表

以下为一些重要的环境变量及其默认行为（可在 .env 覆盖）：

| 变量名 | 说明 | 默认值 |
|---|---|---|
| DATABASE_URL | 数据库文件路径 | sqlite:///./reward.db |
| AUTH_SECRET_KEY | 鉴权 JWT 的 Secret | 仅重启单次随机生成 |
| MEDIA_AI_TTS_PROVIDER | 语音合成服务商 | qwen-realtime |
| MEDIA_AI_SHERPA_MODEL_TYPE | 本地 ASR 模型类型 | sense_voice |

*如果 ASR 路径配置错误或找不到文件，系统在运行时不会出错崩溃，但用户的每一次语音输入均将回落为空白文本。*

##  项目开发资料指引
- **接口文档**: [docs/api_contract.md](docs/api_contract.md)
- **协议说明**: [docs/ws_protocol.md](docs/ws_protocol.md)
- **工作流资产**: [dify_orchestration/](dify_orchestration/)
