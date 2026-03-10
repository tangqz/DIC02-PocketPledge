# Study Buddy WebSocket Protocol

本文档描述当前 backend/app/gateway/ws_router.py 的真实行为。

## 连接

- 地址: ws://localhost:12393/ws
- 认证: query 参数 token
- 示例: ws://localhost:12393/ws?token=<JWT>

## 前端上行

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

当前仅记录日志，不触发实际中断。

### frontend-playback-complete

当前后端忽略该消息。

## 后端下行

### 初始化握手

连接建立后依次发送:

1. model-info
2. supervision-state-change
3. timer-sync
4. 若余额已为 0，则额外发送 control: downgrade

### Agent 输出

- user-transcript
- agent-text-chunk
- agent-text-end
- audio

### 状态与工具副作用

- supervision-state-change
- timer-sync
- balance-update
- supervision-alert
- tool-call-status
- plan-update
- control

## 当前已实现的 Agent 驱动行为

- 文本中包含“开始”时，setup -> active，并执行真实预扣费
- 文本中包含“暂停”时，active -> paused，但当前审批逻辑是网关内置占位实现
- 文本中包含“继续”或“恢复”时，paused -> active
- 文本中包含“计划”时，会推送一个固定的 plan-update 占位数据
- 连续 3 次截图判定走神，会执行真实罚款并推送余额变化

## 当前未闭环行为

- 前端尚未把 periodic-screenshot 真正持续发送到后端监督链路
- interrupt-signal 未真正打断 TTS/Agent 流
- 会话完成后没有总结写回、记忆入库或 RAG 更新
- 暂停审批没有调用系统 Agent 或历史工具，只是字符串匹配
- plan-update 没有数据库来源，只是固定假数据
