# Study Buddy WebSocket Protocol

本文档描述当前 backend/app/gateway/ws_router.py 的真实行为。系统已弃用 Dify，采用内置的双阶段（Two-phase）本地代理（`AGENT_BACKEND=local`）架构处理对话与业务指令。

## 连接

- 地址: ws://localhost:12393/ws
- 认证: query 参数 token (JWT)
- 示例: ws://localhost:12393/ws?token=<JWT>

## 前端上行 (Client to Server)

### text-input

```json
{
	"type": "text-input",
	"text": "我想暂停一下",
	"images": []
}
```

### mic-audio-data

```json
{
	"type": "mic-audio-data",
	"audio": [0.01, -0.02]
}
```

### mic-audio-end

```json
{
	"type": "mic-audio-end",
	"images": []
}
```

### periodic-screenshot

```json
{
	"type": "periodic-screenshot",
	"images": [
		{
			"source": "screen",
			"data": "<base64>",
			"mime_type": "image/jpeg"
		}
	]
}
```

### interrupt-signal

当前后端会清空当前用户待转写音频缓存；前端在发送该消息前也会本地打断 TTS 播放与待播队列。

```json
{
	"type": "interrupt-signal"
}
```

### frontend-playback-complete

当前后端忽略该消息。

### capture-context-result

响应后端发起的 `request-visual-context` 请求，携带主动截图返回。

```json
{
	"type": "capture-context-result",
	"requestId": "123456",
	"images": [],
	"error": ""
}
```

### set-locale

动态切换角色语言模式 ("zh" 或 "en")。

```json
{
	"type": "set-locale",
	"locale": "zh"
}
```

### set-character

动态切换伴学角色 (如 "milly" 或 "ren")。

```json
{
	"type": "set-character",
	"characterId": "ren"
}
```

### resume-now

主动触发恢复专注动作。

```json
{
	"type": "resume-now"
}
```

### ping

心跳保活检测。后端回复 `pong` control。

```json
{
	"type": "ping"
}
```

## 后端下行 (Server to Client)

### 初始化握手

连接建立后依次发送:

1. `model-info`: 当前角色模型配置信息。
2. `supervision-state-change`: 状态流转（setup / active / paused / completed）。
3. `timer-sync`: 当前倒计时同步。
4. `plan-update` (可选): 若当前有活跃的学习计划，则下发。
5. `control` (downgrade): 若余额为 0，下发降级控制指令。

### Agent 输出流 (Streaming Response)

- `user-transcript`: 发送由于 ASR 转写产生的用户文本（供前端气泡展示）。
- `agent-text-chunk`: LLM 推理生成的文本切片。
- `agent-text-end`: 本轮生成结束标志。
- `audio`: 生成的语音切片（带有面部表情动作和对应的字幕）。

### 状态与工具副作用 (Side Effects)

- `supervision-state-change`: 专注状态变更。
- `timer-sync`: 倒计时更新。
- `balance-update`: 金额变化通知。
- `supervision-alert`: 注意力走神警告（带 severity 强度与走神次数）。
- `tool-call-status`: 系统后台执行指令的状态指示（例如：calling, success, error）。
- `plan-update`: 用户学习计划数据的实时同步更新。
- `control`: 下发特定指令（如：`downgrade`、`pong`、`set-expression`、`chat-cleared`、`request-visual-context`）。

## 本地 Agent 驱动行为 (Two-phase Workflow)

系统采用了基于标记的双阶段本地系统驱动流，流程如下：

1. 用户的每一轮发言会先发给“白脑”（Chat Agent）进行闲聊和意图判断。
2. 若白脑判断需要系统交互，会触发内部标记 `<<SYS>>` 或主动环境感知标记 `<<CAPTURE>>`。
3. 如果遇到 `<<SYS>>` 标记，流程会阻断，并调用本地后台的 System Agent 生成强类型的业务指令（start, pause, resume, plan, complete）。
4. 系统根据指令发起后端操作，如果执行前需要视觉确认（如：检查开始专注时的全屏共享与环境机位），会向前端下发 `request-visual-context` `control` 消息。
5. 前端收到后主动触发截屏并回传 `capture-context-result` 供环境准备判断 (`start-readiness`)。
6. 指令处理结束后生成一段系统状态上下文 `[SYSTEM_RESULT: ...]`，并作为透明轮次重新喂给白脑，进行带有业务结果反馈的回复。

### 核心业务场景：

- **Start Session**：根据对话内容检测启动意图，并必须依赖环境截屏与用户画像基础数据准备度进行校验，合格后扣费进入 active 状态。
- **Pause Negotiation**：如果申请暂停，系统通过 System Agent 结合画像和对话上下文裁定批准或拒绝。
- **Resume/Complete**：自动结束专注或恢复专注同步计时。
- **Plan Generation**：持久化学习计划并通过 `plan-update` 推送。
- **Distraction Penalty**：通过 `periodic-screenshot` 上传截图，基于多模态 AI（`evaluate_vision`）进行连续判断，连续3次违规触发真实扣费（`deduct_penalty`）。
- **Profile Memory Rollover**：积累的历史对话通过系统在闲置时通过抽取并沉淀入用户长期记忆（User Profile）。

## 当前未闭环行为

- RAG 用户个性化信息写回检索暂时仍受限，需要更完善的历史总结自动化归档机制。
- 会话总结虽然沉淀入库（`session_summaries`），但还没有作为定期反馈在前端进行日历面板式的展示。
