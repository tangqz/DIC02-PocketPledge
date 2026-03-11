# DIC02-PocketPledge

这是一个面向学习监督场景的陪伴式系统原型。前端提供 Live2D 交互式学习伙伴界面，后端负责账户、专注会话、监督状态同步和 WebSocket 网关，Dify 工作流负责对话、视觉判定和系统代理决策。

## 项目简介

核心目标：把“陪伴聊天”“学习监督”“经济激励/惩罚”放到同一条交互链路中。

当前仓库主要包含以下几部分：

- frontend/：React + TypeScript + Vite 前端，负责聊天 UI、Live2D 展示、音频输入、截图采集和 WebSocket 通信。
- backend/：FastAPI 后端，负责认证、钱包/惩罚结算、专注会话状态、WebSocket 网关和 Dify 代理。
- dify_orchestration/：Dify 编排资产，包含聊天、视觉判定、系统代理工作流与 persona 配置。
- docs/：后端 REST 合同与 WebSocket 协议文档。
- Open-LLM-VTuber/：上游参考项目与资源，不是当前主要开发入口。

## 系统结构

当前链路可概括为：

1. 前端通过 WebSocket 与 backend 建立长连接。
2. 用户输入文本、语音或截图后，网关根据场景调用聊天、视觉判定或系统代理。
3. 聊天负责自然语言陪伴回复；需要执行动作时，通过 `<<SYS>>` 触发系统代理。
4. 系统代理返回结构化指令，后端执行开始专注、暂停、继续、完成、计划更新、请求视觉上下文等动作。
5. 视觉判定对截图做分心判定；连续命中阈值后，后端执行真实罚金扣除并更新余额。

当前后端已经实现的关键能力：

- JWT 注册、登录和当前用户查询
- 专注会话启动与预扣费
- 分心罚金结算
- 用户余额/破产状态查询
- WebSocket 状态同步、文本流式回复、音频下发
- Dify 聊天、系统代理、视觉判定代理接入

## 目录总览

```text
frontend/                React 前端
backend/                 FastAPI 后端
dify_orchestration/      Dify 工作流与 persona
docs/                    接口与协议文档
DevelopmentPlan/         开发计划文档
Open-LLM-VTuber/         参考工程与素材
```

## 前端安装与运行

### 1) 环境要求

- Node.js 20+
- npm 10+

### 2) 安装依赖

```bash
cd frontend
npm install
```

### 3) 启动开发环境

打开两个终端：

终端 A，启动前端页面：

```bash
cd frontend
npm run dev
```

终端 B，可选启动本地 Mock WebSocket 服务：

```bash
cd frontend
npm run mock
```

默认行为：

- 前端默认连接 `ws://localhost:12393/ws`
- 如果已经启动真实后端，则通常不需要再运行 `npm run mock`

### 4) 生产构建与预览

```bash
cd frontend
npm run build
npm run preview
```

### 5) 常用脚本

- `npm run dev`：启动 Vite 开发服务器
- `npm run mock`：启动本地 WebSocket Mock 服务
- `npm run build`：类型检查并构建生产包
- `npm run preview`：预览打包产物
- `npm run lint`：运行 ESLint

## 后端安装与运行

### 1) 环境要求

- Python 3.10+
- 建议使用虚拟环境或 conda 环境

### 2) 安装依赖

```bash
cd backend
python -m pip install -r requirements.txt
```

当前主要依赖包括：

- fastapi
- uvicorn
- sqlalchemy
- pydantic
- httpx
- dashscope
- edge-tts
- sherpa-onnx
- onnxruntime

### 3) 启动后端服务

在仓库根目录执行：

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 12393 --reload
```

Windows 本地联调也可以直接双击或执行根目录脚本：

```bat
start-dev.cmd
```

该脚本会分别拉起前端和后端两个 PowerShell 窗口。

后端会在启动时自动读取以下本地配置文件：

- `backend/.env`
- 仓库根目录 `.env`

优先级规则：如果系统环境变量已存在，则不会被 `.env` 覆盖。

启动后默认服务地址：

- HTTP: `http://localhost:12393`
- WebSocket: `ws://localhost:12393/ws?token=<JWT>`
- 健康检查: `http://localhost:12393/health`

### 4) 数据库

- 默认数据库为 SQLite：`backend/reward.db`
- 数据库连接通过 `DATABASE_URL` 配置
- 服务启动时会自动建表并初始化系统账户与一个测试用户

初始化时默认会创建：

- `charity_sink` 系统账户
- `reward_pool` 系统账户
- `demo_user_2` 测试用户

### 5) 认证与默认行为

- 后端使用自实现 JWT，密钥来自 `AUTH_SECRET_KEY`
- 默认 token 有效期来自 `AUTH_TOKEN_EXPIRE_MINUTES`，默认 1440 分钟
- 注册用户默认初始余额来自 `AUTH_INITIAL_BALANCE`，默认 3000

## 后端环境变量

常用环境变量如下：

| 变量名 | 说明 | 默认值 |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy 数据库连接串 | `sqlite:///./reward.db` |
| `AUTH_SECRET_KEY` | JWT 签名密钥 | 启动时随机生成 |
| `AUTH_TOKEN_EXPIRE_MINUTES` | JWT 过期时间 | `1440` |
| `AUTH_INITIAL_BALANCE` | 新用户初始余额 | `3000` |
| `MEDIA_AI_USE_REAL_DIFY` | 是否启用真实 Dify | `0` |
| `MEDIA_AI_ASR_PROVIDER` | 本地语音转写提供方 | `sherpa-onnx` |
| `MEDIA_AI_TTS_PROVIDER` | 本地语音合成提供方 | `qwen-realtime` |
| `MEDIA_AI_TTS_MODEL` | Qwen 实时 TTS 模型 | `qwen3-tts-instruct-flash-realtime` |
| `MEDIA_AI_TTS_VOICE` | Qwen TTS 音色 | `Cherry` |
| `MEDIA_AI_TTS_MODE` | Qwen TTS 提交模式 | `server_commit` |
| `MEDIA_AI_TTS_SPEECH_RATE` | Qwen TTS 语速 | `1.05` |
| `MEDIA_AI_TTS_ENABLE_TN` | Qwen TTS 是否启用文本归一化 | `1` |
| `MEDIA_AI_SHERPA_MODEL_TYPE` | sherpa-onnx 模型类型 | `sense_voice` |
| `MEDIA_AI_SHERPA_MODEL_PATH` | SenseVoice ONNX 模型路径 | `Open-LLM-VTuber/models/.../model.int8.onnx` |
| `MEDIA_AI_SHERPA_TOKENS_PATH` | sherpa-onnx tokens.txt 路径 | `Open-LLM-VTuber/models/.../tokens.txt` |
| `MEDIA_AI_SHERPA_NUM_THREADS` | sherpa-onnx 线程数 | `2` |
| `MEDIA_AI_SHERPA_PROVIDER` | sherpa-onnx 推理设备 | `cpu` |
| `MEDIA_AI_SHERPA_USE_ITN` | SenseVoice 是否开启 ITN | `1` |
| `DIFY_API_BASE` | Dify API 基址 | 空 |
| `DIFY_CHAT_ENDPOINT` | 聊天接口路径 | `/v1/chat-messages` |
| `DIFY_FILE_UPLOAD_ENDPOINT` | Dify 文件上传路径 | `/v1/files/upload` |
| `DIFY_VISION_ENDPOINT` | 视觉判定工作流接口路径 | `/v1/workflows/run` |
| `DIFY_SYSTEM_AGENT_ENDPOINT` | 系统代理工作流接口路径 | `/v1/workflows/run` |
| `DIFY_CHAT_API_KEY` | 聊天 Dify API Key | 空 |
| `DIFY_VISION_API_KEY` | 视觉判定 Dify API Key | 默认继承聊天 Key |
| `DIFY_SYSTEM_AGENT_API_KEY` | 系统代理 Dify API Key | 默认继承聊天 Key |
| `DIFY_TOOL_BEARER_TOKEN` | Dify 自定义工具固定 Bearer Token | 空 |

如果不配置真实 Dify，后端会回退到本地 Mock 行为，便于联调前端和网关逻辑。

### Qwen Realtime TTS

当前默认 TTS 已切到 DashScope 的 Qwen 实时语音合成，目标是尽量降低陪伴对话首包延迟，同时保持前端音频协议不变。

实现方式：

- 后端调用 `qwen3-tts-instruct-flash-realtime`
- 输出格式固定为 `PCM_24000HZ_MONO_16BIT`
- 后端把返回的 PCM 封装为 WAV，再按现有 WebSocket `audio` 消息下发给前端
- API Key 默认优先读取 `MEDIA_AI_TTS_API_KEY`，否则依次回退到 `DASHSCOPE_API_KEY`、`LOCAL_AGENT_API_KEY`、`LOCAL_CHAT_API_KEY`

如果你已经在 `.env` 中配置了同一套 DashScope / Qwen Key，通常不需要再额外复制一份 TTS key。

### Sherpa-ONNX ASR

当前后端默认不再走 faster-whisper，而是切到与 Open-LLM-VTuber 同思路的 sherpa-onnx SenseVoice 方案。

请区分两类模型目录：

- ASR 模型：`sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`
- TTS 模型：例如 `kokoro-multi-lang-v1_1`

你刚才提到的那份 TTS 模型不是 ASR。当前后端 ASR 只会读取 SenseVoice 目录，不会去读 kokoro 之类的 TTS 目录。

你需要自行准备模型文件。默认建议放到：

- `C:/Users/qizhi/Desktop/coding/Open-LLM-VTuber/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/model.int8.onnx`
- `C:/Users/qizhi/Desktop/coding/Open-LLM-VTuber/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/tokens.txt`

我已经核对过这两个文件当前确实存在于上面这个外部项目目录中。后端默认也会优先尝试这个路径；只有找不到时，才会回退尝试仓库内的 `Open-LLM-VTuber` 子目录。

如果你的模型不在这个位置，请通过环境变量覆盖：

- `MEDIA_AI_SHERPA_MODEL_PATH`
- `MEDIA_AI_SHERPA_TOKENS_PATH`

如果模型文件不存在，后端不会改用 whisper，而是记录错误并让该次语音输入回落为空转写。

## 调试日志

当前后端默认会打印以下调试信息：

- HTTP API 请求与响应摘要
- WebSocket 上下行消息摘要
- 本地 chat / system / vision 模型请求与响应摘要

这些日志会直接输出在后端终端里，便于本地联调时追踪一整条请求链路。

## Dify 自定义工具

给 Dify 导入的自定义工具 OpenAPI 文件已经放到：

- [dify_orchestration/tools/study_buddy_custom_tools.openapi.yaml](dify_orchestration/tools/study_buddy_custom_tools.openapi.yaml)
- [dify_orchestration/tools/README.md](dify_orchestration/tools/README.md)

这份定义遵循 OpenAPI 3.0.3 兼容写法。根据 Swagger/OpenAPI 规范，根文档至少应该明确：

- `openapi`
- `info`
- `servers`
- `paths`
- `components`

同时，为了让 Dify 正确识别认证与结构化输入输出，这份工具定义里还显式声明了：

- `components.securitySchemes.BearerAuth`
- 每个操作唯一的 `operationId`
- `requestBody` 的 `application/json` schema
- 结构化 `responses`

注意：这份工具定义现在面向 system agent 的内部工具调用，采用固定 Bearer + 显式 `user_id` 传参，不再依赖普通用户 JWT 的 `me` 语义。

Swagger 规范入口文档：

- https://swagger.io/specification/

### 真实 Dify 联调

当前仓库已经支持通过 `backend/.env` 直接切到真实 Dify。

联调前请确认：

- `MEDIA_AI_USE_REAL_DIFY=1`
- `DIFY_API_BASE` 指向你的 Dify 服务根地址；如果 Dify 不在默认端口，请显式带上端口，例如 `http://your-host:8088/v1`
- 三个 API Key 分别对应聊天 Agent、系统 Agent、视觉判定工作流

如果只想本地跑界面和网关逻辑，不想连外部 Dify，把 `MEDIA_AI_USE_REAL_DIFY` 改回 `0` 即可。

## 接口说明

### REST API

默认基址：`http://localhost:12393`

当前已实现接口包括：

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/business/session/start`
- `POST /api/business/penalty/execute`
- `GET /api/business/me/status`
- `GET /api/business/users/{user_id}/status`
- `GET /health`

详细字段说明见 [docs/api_contract.md](docs/api_contract.md)。

### WebSocket

- 地址：`ws://localhost:12393/ws?token=<JWT>`
- 上行消息包括：`text-input`、`mic-audio-data`、`mic-audio-end`、`periodic-screenshot`
- 下行消息包括：`agent-text-chunk`、`agent-text-end`、`audio`、`supervision-state-change`、`timer-sync`、`balance-update`、`plan-update`、`control`

详细协议见 [docs/ws_protocol.md](docs/ws_protocol.md)。

## Dify 编排说明

当前主编排文件位于 [dify_orchestration/workflows](dify_orchestration/workflows)。

其中：

- `white_brain.chat.yml`：白脑陪伴聊天
- `black_brain.workflow.yml`：黑脑视觉分心判定
- `system_agent.workflow.yml`：系统代理，负责把自然语言请求转成结构化动作

当前网关已支持两阶段系统触发机制：

1. 聊天 Agent 先输出过渡语。
2. 若回复中包含 `<<SYS>>`，后端触发系统代理。
3. 后端执行指令后，将 `[SYSTEM_RESULT: ...]` 回灌给聊天 Agent。
4. 聊天 Agent 输出最终面向用户的实质回复。

## 当前推荐开发入口

如果你的目标是继续开发本项目，推荐从以下入口开始：

1. 前端交互与界面：查看 [frontend](frontend)
2. WebSocket 行为与状态流转：查看 [backend/app/gateway/ws_router.py](backend/app/gateway/ws_router.py)
3. 业务账户与结算：查看 [backend/app/business](backend/app/business)
4. Dify 工作流提示词与编排：查看 [dify_orchestration/workflows](dify_orchestration/workflows)

## 相关文档

- [docs/api_contract.md](docs/api_contract.md)
- [docs/ws_protocol.md](docs/ws_protocol.md)
- [DevelopmentPlan/plan.md](DevelopmentPlan/plan.md)

## 当前状态说明

这是一个仍在快速迭代中的原型仓库。部分能力已经打通真实链路，部分能力仍是占位或半闭环实现，例如：

- 计划管理尚未完整持久化
- 前端周期截图监督链路仍需继续联调
- RAG 记忆写回与会话总结尚未闭环
- 一部分系统能力仍依赖 Dify 工作流提示词与外部配置
