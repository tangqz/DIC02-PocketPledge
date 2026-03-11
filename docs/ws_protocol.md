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

当前后端会清空当前用户待转写音频缓存；前端在发送该消息前也会本地打断 TTS 播放与待播队列。

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
- 文本中包含“暂停”时，网关会先走白脑 `<<SYS>>` 触发，再调用 system agent 返回结构化审批结果
- 文本中包含“继续”或“恢复”时，paused -> active
- 文本中包含“计划”时，会持久化并推送真实的 plan-update 数据
- 连续 3 次截图判定走神，会执行真实罚款并推送余额变化

补充说明：

- `request-visual-context` 现在会带上 `requestId`，后端会校验 `capture-context-result.requestId` 是否匹配当前挂起请求。
- plan-update 不再只是内存占位数据，后端会持久化到数据库中的 `study_plans` 表。
- 暂停申请的审批结果会持久化到 `pause_requests` 表。
- 会话完成后，后端会写入一条基础 `session_summaries` 记录，供后续 RAG 或系统 Agent 使用。

## 当前未闭环行为

- 会话完成后没有总结写回、记忆入库或 RAG 更新
- 暂停审批的真正“历史查询 + 用户画像综合决策”仍依赖 Dify 工具编排接入
- 白脑 / 系统 Agent 工作流中的知识检索节点仍需在 Dify 侧绑定真实数据集
- system agent 若要在 Dify 内直接查用户历史，需要使用固定 Bearer + `user_id` 显式传参的内部工具接口
