# 后端接口文档（Frontend 对接版）

本文档面向后端同学，描述当前前端实际使用的协议契约。**以 `frontend/src/lib/protocol.ts` 为单一事实来源**。

## 1. 连接信息

- 协议：WebSocket
- 默认地址：`ws://localhost:12393/ws`
- 传输格式：UTF-8 JSON 文本
- 鉴权：当前版本未内置（如需鉴权，建议通过 query/header + 首包鉴权扩展）

---

## 2. 消息方向概览

- 前端 -> 后端（Tx）：用户输入、语音分片、截图、播放完成回执
- 后端 -> 前端（Rx）：Agent 文本/语音、监督状态、计划与余额更新、计时同步、模型信息

---

## 3. 前端 -> 后端（Tx）

### 3.1 `mic-audio-data`

用于上行语音分片（Float32 样本数组）。

```json
{
  "type": "mic-audio-data",
  "audio": [0.01, -0.02, 0.03]
}
```

字段：
- `audio: number[]` 语音样本

### 3.2 `mic-audio-end`

表示一次语音输入结束，可携带截图证据。

```json
{
  "type": "mic-audio-end",
  "images": [
    {
      "source": "camera",
      "data": "<base64-jpeg>",
      "mime_type": "image/jpeg"
    }
  ]
}
```

字段：
- `images?: SnapshotImage[]`

### 3.3 `text-input`

文本输入（聊天框、按钮意图文本等）。

```json
{
  "type": "text-input",
  "text": "我想暂停5分钟",
  "images": []
}
```

字段：
- `text: string`
- `images?: SnapshotImage[]`

### 3.4 `interrupt-signal`

用户打断 Agent 播放时发送。

```json
{
  "type": "interrupt-signal",
  "text": "已播放到这里的文本"
}
```

字段：
- `text: string`

### 3.5 `periodic-screenshot`

定时监督截图上行。

```json
{
  "type": "periodic-screenshot",
  "images": [
    {
      "source": "screen",
      "data": "<base64-jpeg>",
      "mime_type": "image/jpeg"
    }
  ]
}
```

字段：
- `images: SnapshotImage[]`

### 3.6 `frontend-playback-complete`

前端音频播放完成回执。

```json
{
  "type": "frontend-playback-complete"
}
```

---

## 4. 后端 -> 前端（Rx）

### 4.1 Agent 输出类

#### `agent-text-chunk`

流式文本分片。

```json
{ "type": "agent-text-chunk", "text": "我们先从第一章开始" }
```

#### `agent-text-end`

本轮流式文本结束标记。

```json
{ "type": "agent-text-end" }
```

#### `audio`

TTS 音频与表情动作。

```json
{
  "type": "audio",
  "audio": "<base64-wav>",
  "actions": { "expressions": ["happy"] },
  "display_text": { "text": "做得很好！", "name": "Study Buddy" }
}
```

字段：
- `audio: string` base64 WAV
- `actions.expressions: string[]` 表情关键字列表
- `display_text.text: string`
- `display_text.name: string`

### 4.2 UI 状态同步类

#### `supervision-state-change`

监督状态机更新。前端**只消费后端状态**，不自行切换。

```json
{
  "type": "supervision-state-change",
  "state": "active",
  "duration": 1500,
  "task": "完成两章阅读",
  "pauseDuration": 300,
  "reason": "approved pause"
}
```

字段：
- `state: "setup" | "active" | "paused" | "completed"`
- `duration?: number` 总时长（秒）
- `task?: string`
- `pauseDuration?: number`（秒）
- `reason?: string`

#### `balance-update`

```json
{
  "type": "balance-update",
  "balance": 95,
  "change": -5,
  "reason": "检测到分心"
}
```

字段：
- `balance: number`
- `change: number`
- `reason: string`

#### `plan-update`

```json
{
  "type": "plan-update",
  "plan": {
    "tasks": [
      { "id": "t1", "title": "完成第一章", "completed": false, "estimatedMinutes": 30 }
    ],
    "totalMinutes": 60,
    "suggestedDuration": 3600
  }
}
```

字段：
- `plan.tasks[].id: string`
- `plan.tasks[].title: string`
- `plan.tasks[].completed: boolean`
- `plan.tasks[].estimatedMinutes?: number`
- `plan.totalMinutes: number`
- `plan.suggestedDuration?: number`（秒）

#### `timer-sync`

```json
{
  "type": "timer-sync",
  "remainingSeconds": 1200,
  "totalSeconds": 1500
}
```

#### `supervision-alert`

```json
{
  "type": "supervision-alert",
  "message": "请专注当前任务",
  "severity": "soft",
  "streakCount": 2
}
```

字段：
- `severity: "soft" | "hard"`
- `streakCount?: number`

#### `tool-call-status`

```json
{
  "type": "tool-call-status",
  "tool": "plan.update",
  "status": "calling",
  "message": "updating plan"
}
```

字段：
- `status: "calling" | "success" | "error"`

### 4.3 Live2D / 控制类

#### `model-info`

用于初始化模型配置。

```json
{
  "type": "model-info",
  "model_info": {
    "name": "mao_pro",
    "url": "/live2d-models/mao_pro/mao_pro.model3.json",
    "kScale": 0.5,
    "emotionMap": { "happy": 3, "neutral": 0 },
    "idleMotionGroup": "Idle",
    "talkMotionGroup": ""
  }
}
```

#### `control`

通用控制消息（预留扩展）。

```json
{
  "type": "control",
  "command": "reset-session"
}
```

---

## 5. 状态机约定

监督状态迁移（后端主导）：

- `setup` -> `active`（如工具 `supervision.start`）
- `active` -> `paused`（如工具 `supervision.pause`）
- `paused` -> `active`（如工具 `supervision.resume` 或超时恢复）
- `active|paused` -> `completed`（任务结束/时间到）

前端行为：
- 仅根据 `supervision-state-change` 渲染 UI
- 计时显示以 `timer-sync` 为准

---

## 6. 后端实现建议

- 每个连接维护会话上下文（用户、状态、计时器、最近 plan）
- 所有下行消息严格遵守 `type` 判别联合，避免字段漂移
- `audio` 与 `agent-text-*` 推荐保持同轮次顺序（先 chunk，后 end，再音频或并行都可，但需一致）
- 发生解析失败时记录原始消息并返回可诊断日志（当前前端会在控制台给出 invalid message 警告）

---

## 7. 兼容性说明

- 历史 mock server 中存在 `pause-request/resume-request` 示例消息，它们**不在当前协议的 Tx 定义中**。
- 当前生产约定是：前端通过 `text-input` 表达“暂停/恢复”意图，由 Agent 调用工具并回推 `supervision-state-change`。

---

## 8. 参考代码位置

- 协议类型定义：`frontend/src/lib/protocol.ts`
- WS 连接与分发：`frontend/src/hooks/useWebSocket.ts`
- 顶层发送入口：`frontend/src/App.tsx`
- Mock 服务：`frontend/mock-server.ts`
