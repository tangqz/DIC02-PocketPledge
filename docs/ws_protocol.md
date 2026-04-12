# WarmBuddy WebSocket Protocol

本文档描述当前 `backend/app/gateway/ws_router.py` 的真实行为（陪伴模式）。系统已移除 Dify 运行链，默认使用本地 Agent（`AGENT_BACKEND=local`，可切换 `mock`）。

## 连接

- 地址：`ws://localhost:12393/ws`
- 认证：Query 参数 `token=<JWT>`
- 可选参数：
  - `locale=zh|en`
  - `characterId=milly|ren`

示例：

```text
ws://localhost:12393/ws?token=<JWT>&locale=zh&characterId=milly
```

## 前端上行消息（Client -> Server）

### `text-input`

```json
{
  "type": "text-input",
  "text": "今天有点焦虑，想聊聊",
  "images": []
}
```

### `mic-audio-data`

```json
{
  "type": "mic-audio-data",
  "audio": [0.01, -0.02]
}
```

### `mic-audio-end`

```json
{
  "type": "mic-audio-end",
  "images": []
}
```

### `periodic-screenshot`

```json
{
  "type": "periodic-screenshot",
  "images": [
    {
      "source": "camera",
      "data": "<base64>",
      "mime_type": "image/jpeg"
    }
  ]
}
```

### `interrupt-signal`

用于打断当前语音播放与回复流。

### `capture-context-result`

响应后端下发的 `request-visual-context`：

```json
{
  "type": "capture-context-result",
  "requestId": "req_xxx",
  "prompt": "你看看我状态",
  "images": [
    {
      "source": "camera",
      "data": "<base64>",
      "mime_type": "image/jpeg"
    }
  ]
}
```

### `set-locale`

```json
{
  "type": "set-locale",
  "locale": "en"
}
```

### `set-character`

```json
{
  "type": "set-character",
  "characterId": "ren"
}
```

### `page-opened`

前端在认证通过并挂载主陪伴页面后发送一次，用于触发“打开网页主动问候”。

```json
{
  "type": "page-opened"
}
```

### `ping`

心跳保活，后端会返回 `control: pong`。

## 后端下行消息（Server -> Client）

### 握手阶段

连接建立后下发：

1. `model-info`（当前角色 + Live2D 配置）
2. 当前页面随后由前端主动发送 `page-opened`，后端据此流式下发首句问候（`agent-text-chunk` / `agent-text-end`，并可伴随音频流）

### 文本与语音流

- `user-transcript`：ASR 识别后的用户文本
- `agent-text-chunk`：回复文本流
- `agent-text-end`：本轮文本结束
- `audio`：分段语音（非流式）
- `audio-stream-chunk` / `audio-stream-end`：流式 TTS 音频

### 状态与事件

- `emotion-update`：视觉情绪识别结果
- `tool-call-status`：系统动作执行状态（`calling|success|error`）
- `control`：前端控制命令
  - `set-expression`
  - `request-visual-context`
  - `chat-cleared`
  - `pong`

## 双阶段编排（Two-phase）

系统采用白脑优先的双阶段流程：

1. 白脑先生成自然回复（流式输出）。
2. 若回复中包含 `<<CAPTURE>>`：后端请求前端采集视觉上下文。
3. 若回复中包含 `<<SYS>>`：后端调用 system agent，执行结构化动作（如情绪记录、画像更新）。
4. 执行结果以 `[SYSTEM_RESULT: ...]` 再喂回白脑，生成对用户可见的自然表达。

## 已移除的旧协议

以下旧监督模式消息不再使用：

- `supervision-state-change`
- `timer-sync`
- `plan-update`
- `balance-update`
- `supervision-alert`
