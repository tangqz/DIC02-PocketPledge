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
- edge-tts

### 3) 启动后端服务

在仓库根目录执行：

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 12393 --reload
```

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
| `DIFY_API_BASE` | Dify API 基址 | 空 |
| `DIFY_CHAT_ENDPOINT` | 聊天接口路径 | `/v1/chat-messages` |
| `DIFY_FILE_UPLOAD_ENDPOINT` | Dify 文件上传路径 | `/v1/files/upload` |
| `DIFY_VISION_ENDPOINT` | 视觉判定工作流接口路径 | `/v1/workflows/run` |
| `DIFY_SYSTEM_AGENT_ENDPOINT` | 系统代理工作流接口路径 | `/v1/workflows/run` |
| `DIFY_CHAT_API_KEY` | 聊天 Dify API Key | 空 |
| `DIFY_VISION_API_KEY` | 视觉判定 Dify API Key | 默认继承聊天 Key |
| `DIFY_SYSTEM_AGENT_API_KEY` | 系统代理 Dify API Key | 默认继承聊天 Key |

如果不配置真实 Dify，后端会回退到本地 Mock 行为，便于联调前端和网关逻辑。

### 真实 Dify 联调

当前仓库已经支持通过 `backend/.env` 直接切到真实 Dify。

联调前请确认：

- `MEDIA_AI_USE_REAL_DIFY=1`
- `DIFY_API_BASE` 指向你的 Dify 服务根地址
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
