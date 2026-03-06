# 请注意，此文档已经过时。作为AI Agent，以下内容仅供参考，请以用户的实际需求提示为准。

---

## Plan: 自律Agent——从参考项目借鉴到自研架构（修订稿 v2 DRAFT）

**TL;DR** — 你们的产品核心是「监督 + 陪伴 + 经济激励」三位一体。Open-LLM-VTuber 提供了一条成熟的流式多模态会话管线（WebSocket 通信、ASR/TTS/VAD 可插拔、MCP 工具调用、角色提示词模块化），这些可以作为架构参考而非直接依赖。下面按「**借什么、改什么、自建什么**」三层拆解。

---

### 一、可直接借鉴的架构思路

1. **MCP 工具调用体系** — 参考 tool_adapter.py + tool_executor.py 的「注册→Schema 构建→执行→状态回传」管线。你们的**奖惩系统、计划管理、打卡、计时器**均可实现为独立 MCP Server，Agent 只做调用方。注册只需修改 mcp_servers.json 级别的声明式配置，非常轻量。

2. **模块化提示词框架** — 参考 prompt_loader.py + prompts/utils/ 的组装逻辑：`persona_prompt` + 可选模块（表情、工具指导、口语化、简洁模式）拼接为系统提示。你们可以新增 `supervision_rules_prompt.txt`、`reward_punishment_prompt.txt`、`negotiation_prompt.txt` 等模块，按场景动态组合。

3. **WebSocket + 前端状态机通信模式** — 参考 websocket_handler.py 的消息协议设计（`mic-audio-end`、`interrupt-signal`、`tool_call_status` 等）。你们需要扩展的消息类型（`pause-signal`、`resume-signal`、`periodic-screenshot`、`environment-check-result`）可按相同模式设计。

4. **ASR/TTS/VAD/LLM 可插拔工厂** — 参考四个工厂（asr_factory.py、tts_factory.py、vad_factory.py、stateless_llm_factory.py）的注册-切换模式。你们可以沿用同样的工厂抽象，方便未来切换模型供应商。

5. **图像输入编码管线** — 参考 input_types.py 的 `BatchInput` + `ImageData` 结构，以及 basic_memory_agent.py 中图像编为 Vision API 消息的逻辑。摄像头与屏幕截图的 Canvas→Base64→WS→LLM 这条通路已经验证过。

---

### 二、需要改造/扩展的部分

6. **截图触发机制：从被动到主动** — 原项目截图仅在 `mic-audio-end` 时触发（与语音轮次耦合）。你们需要：
   - 前端新增**定时截图器**（如每 15-30 秒 `setInterval` → `captureAllMedia()` → WS 发送 `periodic-screenshot`）。
   - 后端新增消息处理分支：将 `periodic-screenshot` 路由至监督判定管线而非对话管线。
   - 可选：Agent 通过 MCP 工具调用 `request-screenshot`，后端向前端推送截图请求。

7. **会话状态扩展：新增暂停/协商** — 原项目中断是硬中断（`task.cancel()`），不可恢复。你们需要：
   - 新增 `supervision_state`: `setup` → `active` → `paused` → `active` → `completed`。
   - `pause-signal` / `resume-signal` WS 消息冻结/恢复定时截图与监督判定。
   - 「讨价还价」不需要额外状态机——Agent 在 `active` 状态下通过对话理解用户的暂停请求，调用 MCP 工具（如 `supervision.pause(duration=300, reason="bathroom")`）执行状态切换。这样讨价还价逻辑完全由提示词 + 工具调用驱动，保持架构简洁。

8. **环境引导阶段** — 原项目无此概念。你们需要：
   - 在 `setup` 状态下，Agent 主动请求截图，分析光线/距离/角度（通过 Vision API）。
   - 循环「截图→分析→指导→再截图」直到 Agent 判定条件满足。
   - 可设计为一个 MCP 工具 `environment.check(image)` 返回结构化评分，Agent 据此决定是否进入 `active`。

9. **Agent 主动发起对话** — 原项目有 proactive_speak_prompt.txt 的概念但主要用于群聊闲聊。你们需要事件驱动的主动对话：
   - 监督管线检测到分心 → 触发事件 → Agent 收到事件上下文 → 主动发起提醒/安慰。
   - 计时器到期（如番茄钟结束/暂停超时） → 触发 Agent 主动提醒恢复。

---

### 三、需要完全自建的部分（差异化核心）

10. **奖惩系统（外部 LLM Workflow）** — 这是你们的核心创新点，必须独立于 Agent：
    - 实现为独立服务 + MCP Server 接口，Agent 可调用 `reward.query_balance()`、`reward.record_event(type, evidence, confidence)` 等工具。
    - 内部用 LLM Workflow（如 LangGraph/Dify/自研）做「先提醒 → 置信度达标 → 扣款」的分级决策。
    - 审计日志：每次变更附带截图证据、置信度、时间戳、是否经过提醒。

11. **监督判定管线** — 接收定时截图，做多信号融合判定：
    - 人脸在位检测（本地轻量模型如 MediaPipe/InsightFace）。
    - 注意力/视线估计（可选，精度按设备降级）。
    - 屏幕应用分类（电子学习模式下，OCR/窗口标题匹配）。
    - 输出：`{status: focused|distracted|absent, confidence, evidence_snapshot}`。
    - 该管线不经过 LLM，直接用 CV 模型 + 规则引擎，保证低延迟与确定性。

12. **情感状态与长期记忆层** — 原项目的 `_memory` 是纯列表，无上下文窗口管理，`mem0_agent` 未实现：
    - 引入摘要机制（定期将长对话压缩为摘要）或向量检索（RAG）。
    - 新增情感状态持久化：亲密度指标、历史情绪轨迹、关键事件标签（如「用户坚持了3小时」「用户今天被扣款后很沮丧」）。
    - 这些状态可通过 MCP 工具让 Agent 读写，使其在跨 session 时保持情感连续性。

13. **计费/服务费系统** — 按陪伴时长计费的逻辑完全自建：
    - 后端计时器跟踪 `active` 状态时长。
    - 定价规则引擎（按分钟/按 session/阶梯定价）。
    - 与奖惩系统共享账本，但分离计费事件与奖惩事件。

---

### 四、架构拓扑建议

```
用户 ←→ 前端（WebSocket + Camera/Screen）
         ↕
      会话网关（FastAPI + WS）
         ↕                    ↕
   对话 Agent（LLM）    监督判定管线（CV模型+规则）
     ↕ MCP调用              ↕ 事件推送
  ┌──┴──┬──────┐         ┌──┴──┐
  奖惩系统  计划管理  情感状态  审计日志
 (LLM Workflow) (MCP Server) (MCP Server)
```

---

### Verification

- **环境引导**：模拟不同光线/角度/距离截图，验证 Agent 能给出有效调整建议并正确判断「条件满足」。
- **监督闭环**：模拟分心场景 → 判定管线输出 → 先提醒 → 仍不改 → 扣款 → Agent 安慰，全链路端到端测试。
- **讨价还价**：模拟用户请求暂停 → Agent 协商 → 调用 `supervision.pause()` → 超时提醒 → 恢复，状态转换正确。
- **情感连续性**：跨 session 验证 Agent 是否记住之前的情感事件并做出恰当回应。
- **误判保护**：低置信度事件不触发扣款，仅触发软提醒；用户可查看证据截图。

### Decisions

- **奖惩系统独立于 Agent**：Agent 只做情感陪伴与信息传达，不直接决定扣款，通过 MCP 与外部 Workflow 交互。
- **监督判定用 CV 而非 LLM**：保证低延迟、确定性、成本可控；LLM 仅在需要「解读」时介入。
- **讨价还价走对话+工具调用**：不设独立状态机，靠提示词让 Agent 理解意图，靠 MCP 工具执行暂停操作，架构更简洁。
- **情感层通过 MCP 工具读写外部状态**：而非硬编码到 Agent 内部，保持 Agent 可替换性。

---

## Plan: 长期记忆系统设计（修订稿 v3 增量 DRAFT）

**TL;DR** — 当前参考项目的记忆是一个**无限增长的列表 + 全量 JSON 文件**，没有 token 管理、没有摘要、没有跨 session 语义检索。要模拟"每天见面的伴侣"体验，需要建立**三层记忆架构**：工作记忆（当前会话窗口）、情节记忆（历史摘要 + 关键事件）、用户画像（持久化事实与情感状态）。Agent 每次"开工"时像一个真正的伴侣一样——记得你的偏好、知道昨天发生了什么、关心你的进展。

---

### 三层记忆架构

#### 第一层：工作记忆（Working Memory）— 当前 session 上下文窗口

参考原项目 basic_memory_agent.py 中 `_memory` 列表的机制，但**必须新增**：

1. **Token 计数与滑动窗口** — 设定最大 token 预算（如总 context 的 60%，留 40% 给系统提示+工具结果+当前输入）。当 `_memory` 超出预算时，从最早的消息开始移出，移出的消息送入「情节记忆」压缩管线。
2. **重要性标记** — 某些消息不应被滑出（如用户说「我今天的目标是完成三章阅读」、Agent 批准暂停等关键事件），打上 `pinned=True` 标记，滑动窗口跳过它们。
3. **session 开场注入** — 每次新 session 开始时，从第二层（情节记忆）和第三层（用户画像）提取摘要，作为系统提示的一部分注入，让 Agent「记得」之前的一切。

#### 第二层：情节记忆（Episodic Memory）— 历史摘要 + 关键事件

这是**新的持久化层**，原项目完全没有：

4. **Session 结束摘要** — 每个 session 结束（或用户主动关闭）时，用 LLM 对整段对话做一次摘要，提取：
   - 学习了什么/完成了什么
   - 情绪轨迹（开心→疲惫→坚持）
   - 关键对话片段（讨价还价、被扣款后的反应、突破时刻）
   - 未完成事项 / 明天计划

5. **关键事件日志** — 除了摘要，独立存储结构化事件：
   ```
   {type: "achievement", content: "连续专注2小时", timestamp, session_id}
   {type: "penalty", content: "浏览社交媒体被扣5元", evidence_id, timestamp}
   {type: "emotional", content: "被扣款后情绪低落，Agent安慰后恢复", timestamp}
   {type: "negotiation", content: "请求暂停15分钟上洗手间，批准", timestamp}
   {type: "milestone", content: "累计专注时长突破100小时", timestamp}
   ```

6. **语义检索（RAG）** — 对历史摘要和关键事件做 embedding，存入向量数据库（如 ChromaDB/本地 SQLite+向量扩展），Agent 在需要时按语义相关性召回。例如用户说「我上次读到哪了」，可检索出最近一次关于阅读进度的事件。

#### 第三层：用户画像（User Profile）— 持久化事实与关系状态

7. **事实记忆** — Agent 在对话中主动提取并持久化关于用户的事实：
   - 基本信息：名字、年级、专业、学习科目
   - 偏好：喜欢被鼓励还是被刺激、学习习惯（早起型/夜猫子）、常用的学习材料
   - 敏感点：什么话题容易让用户不开心、什么方式的提醒最有效

8. **关系状态** — 量化伴侣关系维度（通过 MCP 工具读写），Agent 的语气和策略据此调整：
   - `trust_level`: 信任度（用户多大程度上接受 Agent 的建议）
   - `familiarity`: 亲密度（互动总时长、session 次数）
   - `recent_mood_trend`: 近期情绪走势
   - `streak_days`: 连续学习天数
   - `total_focus_hours`: 累计专注时长

9. **自适应人格微调** — 根据画像动态调整提示词片段：
   - 新用户：热情、多解释、主动引导
   - 老用户：简洁、默契、偶尔回顾共同记忆（「上次你为了那道数学题纠结了半小时，今天是不是又遇到了？」）
   - 低情绪期：温柔、少压力、主动降低目标建议
   - 高状态期：推一把、建议挑战更高目标

---

### "每日学习伴侣"体验落地

10. **Session 开场仪式** — Agent 每天第一次见面时的行为：
    - 从第三层读取用户画像 → 「早上好 [名字]！昨天你完成了 [X]，今天打算继续吗？」
    - 从第二层检索昨天的 session 摘要 → 提及未完成事项
    - 从关系状态读取连续天数 → 「这是你连续第 [N] 天了！」
    - 如果检测到隔了几天没来 → 「好久不见，想你了。最近是不是忙？」而非冷冰冰重新开始

11. **Session 中的「伴侣感」** — 在专注监督期间：
    - Agent 不只是机械监督，偶尔通过主动对话分享一些与学习主题有关的小知识（从情节记忆中找到用户正在学的科目）
    - 番茄钟休息时回顾「你刚才这段时间专注度很高，比昨天同一时段好」（需要跨 session 数据对比）
    - 记住用户上次提过的烦恼，适时关心

12. **Session 结束仪式** — 用户关闭前：
    - Agent 主动总结今天的成果（调用摘要管线）
    - 与昨天对比 → 「今天比昨天多专注了 40 分钟」
    - 约定明天 → 「明天同一时间见？」
    - 将摘要、事件、更新后的画像全部持久化

---

### 技术实现路径

**Steps**

1. **设计记忆数据模型** — 定义三层记忆各自的 schema（工作记忆条目、情节摘要条目、关键事件条目、用户画像字段），以及它们的存储后端（工作记忆=内存，情节记忆=SQLite+向量索引，用户画像=JSON/KV 存储）。

2. **实现 token 预算管理器** — 替代原项目 `_memory` 的无限增长机制。需要一个 `ContextWindowManager`，接受 `max_tokens` 配置，提供 `add()`、`evict()`、`get_messages()` 方法。滑出的消息通过回调送入压缩队列。参考原项目 `_add_message` 的接口但完全重写内部逻辑。

3. **实现 session 摘要管线** — session 结束时异步调用 LLM 生成结构化摘要（JSON 格式：成果、情绪、关键事件、未完成项）。存入情节记忆层。可参考原项目 `finalize_conversation_turn`（conversation_utils.py）的轮次结束钩子位置来插入摘要触发。

4. **实现语义检索层** — 对情节摘要和关键事件做 embedding 并存入本地向量库（ChromaDB 或 `sqlite-vec`），提供 `retrieve(query, top_k)` 接口。作为 MCP 工具暴露给 Agent：`memory.search(query)` 让 Agent 能主动回忆。

5. **实现用户画像读写** — 作为 MCP 工具暴露：`profile.get()`、`profile.update(field, value)`。Agent 在对话自然流中提取事实并写入。可在提示词中加入指令：「当你了解到用户的新信息时，调用 profile.update 保存」。

6. **实现 session 开场/结束协议** — 在会话网关层增加 `session-start` / `session-end` 生命周期钩子。开场时自动注入画像摘要 + 最近N条情节摘要到系统提示；结束时触发摘要管线 + 画像更新。

7. **实现关键事件实时提取** — 监督管线产生的事件（扣款、奖励、暂停、里程碑）自动写入情节记忆层，无需 Agent 手动调用。Agent 对话中产生的重要信息通过 LLM 判断后自动提取。

---

### Verification

- **上下文窗口**：模拟超长对话（200+轮），验证 token 预算不超限，关键消息（pinned）不被滑出，滑出消息正确进入压缩队列。
- **跨 session 连续性**：关闭 session → 重新打开，验证 Agent 的开场白包含昨天的摘要、用户名字、连续天数。
- **语义检索准确性**：用户问「上次读到哪了」→ Agent 正确召回最近的阅读进度事件。
- **画像积累**：经过 5 个 session 后，检查画像中是否积累了用户偏好、学习科目、情绪模式等信息。
- **存储性能**：100 个 session 后，向量检索响应 < 200ms，画像读取 < 50ms。

### Decisions

- **三层分离而非单一 RAG**：工作记忆保证即时响应质量，情节记忆保证长期语义连续，画像保证人格一致性。比单纯把所有历史塞进 RAG 更可控。
- **摘要而非全量历史**：每天几小时的对话会产生大量消息，全量保存+检索不经济。摘要是有损压缩但大幅降低成本，关键事件独立存储弥补信息丢失。
- **画像字段由 Agent 自主维护**：通过 MCP 工具让 Agent 自行决定何时更新画像，而非用规则引擎硬编码提取逻辑，更符合「伴侣自然了解你」的体验。
- **本地向量库优先**：ChromaDB 或 `sqlite-vec`，避免依赖云端向量服务，降低延迟和成本，也符合隐私优先策略。

---

## Plan: Dify + 外壳服务端 + Web App 架构设计（DRAFT）

**TL;DR** — 将 Dify 作为「AI 大脑」，负责对话编排、Agent 推理、工具调用和知识库检索；外壳服务端作为「业务中枢」，负责实时监督管线、奖惩账本、用户系统和 WebSocket 长连接；前端 Web App 用 **React + Vite + PWA** 构建，通过 Chrome 的 WebRTC 能力实现摄像头/屏幕采集，一套代码覆盖桌面/平板/手机。

---

### 一、Dify 中写什么（AI 层）

Dify 负责所有需要 LLM 推理的部分，通过 API 被外壳服务端调用。

#### 1. 主 Chatflow —「陪伴 Agent」

这是核心应用，类型选 **Chatflow**（支持多轮对话 + `conversation_id` 延续）：

- **Agent 节点**：使用 Function Calling 策略，挂载下述自定义工具，让 LLM 自主决定何时调用。
- **Memory**：开启会话记忆，设置合理的 Window Size（如 20 轮），Dify 会自动管理上下文窗口。
- **System Prompt**（在 Instruction 中写）：角色人设 + 监督规则 + 情感风格 + 工具使用指导。这里写你们的 `persona_prompt`，定义伴侣角色的性格、说话风格、奖惩时的安慰/刺激策略、讨价还价规则等。
- **Vision 开启**：在 LLM 节点开启 Vision 功能，使 Agent 能直接分析传入的摄像头/屏幕截图。
- **Conversation Variables**（会话变量）：用于持久化当前 session 内的关键状态：
  - `supervision_state`: string（`setup` / `active` / `paused` / `completed`）
  - `current_task`: string（当前学习目标）
  - `pause_remaining_seconds`: number
  - `session_start_time`: string
  - `mood`: string（当前情绪判断）

#### 2. 自定义工具插件（Dify Tool Plugin）

开发以下 Dify 插件工具，Agent 在对话中自主调用：

| 工具名 | 功能 | 参数 | 实现方式 |
|---|---|---|---|
| `reward.query_balance` | 查询用户余额和奖惩历史 | `user_id` | HTTP → 外壳服务端 API |
| `reward.record_event` | 记录奖惩事件（扣款/奖励） | `user_id, type, amount, reason, evidence_id` | HTTP → 外壳服务端 API |
| `supervision.pause` | 暂停监督（讨价还价通过后调用） | `user_id, duration_seconds, reason` | HTTP → 外壳服务端 API |
| `supervision.resume` | 恢复监督 | `user_id` | HTTP → 外壳服务端 API |
| `supervision.start` | 环境检查通过后启动监督 | `user_id, mode` | HTTP → 外壳服务端 API |
| `profile.get` | 读取用户画像 | `user_id` | HTTP → 外壳服务端 API |
| `profile.update` | 更新用户画像字段 | `user_id, field, value` | HTTP → 外壳服务端 API |
| `memory.search` | 语义检索历史记忆 | `user_id, query, top_k` | HTTP → 外壳服务端 API |
| `plan.get_today` | 获取今日学习计划 | `user_id` | HTTP → 外壳服务端 API |
| `plan.update` | 更新/创建学习计划 | `user_id, tasks[]` | HTTP → 外壳服务端 API |
| `timer.status` | 查询当前番茄钟/计时状态 | `user_id` | HTTP → 外壳服务端 API |

> **实现方式**：每个工具本质上是向外壳服务端发 HTTP 请求。可以用 Dify Tool Plugin 开发框架（Python ≥ 3.12）封装，也可以直接在 Chatflow 中用 **HTTP Request 节点** 作为简易替代。推荐开发为一个统一的 Tool Plugin 包。

#### 3. 独立 Workflow —「奖惩判定引擎」

与主 Chatflow 分开，由外壳服务端在监督判定后调用：

- **输入**：`{user_id, event_type, confidence, evidence_snapshot, context}`
- **流程**：
  1. **条件判断节点**：confidence < 阈值 → 仅提醒，不扣款
  2. **LLM 节点**：分析证据，确认是否构成违规，生成人类可读的判定描述
  3. **条件分支**：首次 → 发提醒；重复 → 执行扣款
  4. **HTTP Request 节点**：向外壳服务端写入审计日志 + 更新账本
- **输出**：`{decision, amount, description, should_notify_agent}`

#### 4. 知识库

| 知识库 | 内容 | 用途 |
|---|---|---|
| 用户情节记忆库 | 每个 session 的摘要、关键事件（按 user_id metadata 过滤） | Agent 通过 `memory.search` 工具间接查询，或直接在 Chatflow 中以 Knowledge Retrieval 节点接入 |
| 学习方法知识库 | 通用的学习技巧、时间管理方法、番茄钟使用指南等 | Agent 在休息时为用户分享有用技巧 |

> 情节记忆写入知识库：外壳服务端在 session 结束时调用 Dify Knowledge Base API upload 摘要文档，带 `user_id` 和 `date` metadata。Agent 查询时通过 Metadata Filtering 按用户隔离。

#### 5. Session 开场 Prompt 动态注入

外壳服务端在每次新 session 调用 Dify `chat-messages` API 时，将以下信息作为第一条 `query` 的 `inputs` 变量注入：

```
- 用户画像摘要（名字、偏好、连续天数、累计时长）
- 昨天的 session 摘要
- 今日待完成计划
- 当前余额
- 当前时间
```

Agent 据此生成自然的开场白（「早上好xx！昨天你…今天继续吗？」）。

---

### 二、外壳服务端写什么（业务层）

技术栈：**Python + FastAPI + WebSocket + SQLite/PostgreSQL**

#### 6. 核心职责划分

| 模块 | 职责 | 关键技术 |
|---|---|---|
| **WebSocket 网关** | 与前端保持长连接，转发 Agent 消息、推送监督事件 | FastAPI WebSocket |
| **Dify 代理层** | 调用 Dify Chat API（流式SSE），转化为 WS 消息推送前端 | `httpx` SSE streaming |
| **监督判定管线** | 接收定时截图，用 CV 模型做人脸/注意力检测 | MediaPipe / InsightFace |
| **奖惩账本** | 用户余额、交易流水、审计日志 | SQLite/PostgreSQL |
| **用户系统** | 注册、登录、JWT 认证 | FastAPI + JWT |
| **画像服务** | 用户画像 CRUD | JSON 字段或 KV 表 |
| **记忆服务** | 情节摘要存储、向量检索 | ChromaDB / sqlite-vec |
| **计时器服务** | 番茄钟、暂停计时、服务费计时 | asyncio + 内存定时器 |
| **TTS 服务**（可选） | 语音合成，增强伴侣感 | edge-tts / Kokoro |

#### 7. 核心 API 设计

```
# === 前端 WebSocket ===
ws://server/ws/{user_id}
  ← user-message (text + images[])     # 用户发消息
  → agent-message-chunk (streaming)     # Agent 流式回复
  → agent-tool-status                   # 工具调用状态
  → supervision-alert                   # 监督提醒
  → supervision-state-change            # 状态变更
  ← periodic-screenshot                 # 前端定时发截图
  ← pause-request / resume-request      # 用户请求暂停/恢复

# === Dify 工具回调 REST API ===
GET  /api/reward/balance/{user_id}
POST /api/reward/event
POST /api/supervision/pause
POST /api/supervision/resume
POST /api/supervision/start
GET  /api/profile/{user_id}
PATCH /api/profile/{user_id}
POST /api/memory/search
GET  /api/plan/today/{user_id}
PUT  /api/plan/{user_id}
GET  /api/timer/status/{user_id}
```

#### 8. 数据流走向（一次完整交互）

```
用户说话/打字
  → 前端 WS → 外壳服务端
    → 附加当前截图（如有）
    → 调用 Dify chat-messages API (streaming, conversation_id)
      → Dify Agent 推理
        → 可能调用工具 → HTTP回调外壳服务端 → 返回结果给 Dify
      → 流式返回 answer
    → 外壳服务端解析SSE → WS推送前端
  → 前端播放文字 + TTS音频 + 表情

同时（独立管线）：
前端每15秒截图 → WS → 外壳服务端 → CV判定管线
  → 正常：无操作
  → 异常（confidence > 阈值）：
    → 调用 Dify "奖惩判定 Workflow" API
    → 结果：提醒 or 扣款
    → 向主 Chatflow 注入事件消息（如"用户似乎在看手机"）
    → Agent 据此做出安慰/刺激回应
```

---

### 三、前端 Web App 技术框架

#### 9. 技术栈选型

| 层 | 选型 | 理由 |
|---|---|---|
| **框架** | **React 18 + TypeScript** | 生态最大、组件丰富、团队易招人 |
| **构建** | **Vite** | 快速开发体验、HMR |
| **样式** | **TailwindCSS** | 响应式设计开箱即用，一套代码适配桌面/平板/手机 |
| **路由** | **React Router v7** | SPA 路由 |
| **状态** | **Zustand** | 轻量、直觉、适合 WS 状态管理 |
| **WS 通信** | **原生 WebSocket + reconnecting-websocket** | 自动重连、心跳 |
| **摄像头/屏幕** | **WebRTC `getUserMedia` / `getDisplayMedia`** | Chrome 原生支持 |
| **PWA** | **vite-plugin-pwa** | 安装到桌面/手机主屏幕，类原生体验 |
| **UI 组件** | **shadcn/ui** 或 **Ant Design Mobile** | shadcn 桌面优先，antd-mobile 移动优先，按侧重选 |
| **Live2D**（可选） | **pixi-live2d-display** | 如需虚拟形象 |
| **音频** | **Web Audio API + MediaRecorder** | 语音输入 |

#### 10. 跨平台适配策略

| 平台 | 方案 | 注意事项 |
|---|---|---|
| **桌面 Chrome** | 直接访问 Web App | 屏幕共享（`getDisplayMedia`）完整支持 |
| **平板 Chrome** | 同一 Web App，响应式布局自动适配 | 屏幕共享在 Android Chrome 支持，iPad Safari 不支持但 iPad Chrome 可选 |
| **手机 Chrome** | 同一 Web App，PWA 安装 | **手机不支持 `getDisplayMedia`**，仅走「传统学习模式」（纯摄像头） |
| **可选：桌面客户端** | **Electron** 或 **Tauri** 包装 Web App | 需要更深屏幕权限时（如后台监控），但 MVP 阶段不必要 |

> **关键限制**：手机端 Chrome 不支持屏幕共享 API。因此「电子学习模式」仅限桌面/平板，手机端自动降级为「传统学习模式」。前端根据 `navigator.mediaDevices.getDisplayMedia` 是否可用自动判断。

#### 11. 前端核心页面

| 页面 | 功能 |
|---|---|
| **登录/注册** | 用户认证 |
| **主界面** | Agent 对话区 + 状态面板（余额、计时、任务列表） |
| **学习模式选择** | 电子学习 / 传统学习，引导开启摄像头/屏幕共享 |
| **环境校准** | Agent 引导调整光线/角度/距离，实时预览摄像头画面 |
| **专注中** | 简洁界面：计时器 + Agent 小窗 + 快捷暂停按钮 |
| **Session 总结** | 今日成果、与昨日对比、余额变动明细 |
| **历史记录** | 过往 session 列表、奖惩流水 |
| **设置** | 角色偏好、通知、摄像头/屏幕选择 |

---

### 四、部署拓扑

```
┌─────────────────────────────────────────────────┐
│                   云服务器                        │
│                                                  │
│  ┌──────────┐    ┌──────────────────┐            │
│  │  Dify    │    │  外壳服务端       │            │
│  │ (Docker) │◄──►│ (FastAPI+Docker) │            │
│  │          │    │                  │            │
│  │ - Chatflow│   │ - WS网关         │            │
│  │ - Workflow│   │ - CV管线         │            │
│  │ - 知识库  │    │ - 奖惩账本       │            │
│  │ - 工具插件│    │ - 记忆服务       │            │
│  └──────────┘    │ - 用户系统       │            │
│                  └────────┬─────────┘            │
│                           │                      │
│              ┌────────────┴──────────┐           │
│              │   Nginx (反向代理)     │           │
│              │   + 静态前端托管       │           │
│              └───────────────────────┘           │
└─────────────────────────────────────────────────┘
                        ▲
                        │ HTTPS + WSS
              ┌─────────┴─────────┐
              │  Chrome 浏览器     │
              │  (桌面/平板/手机)  │
              └───────────────────┘
```

---

### Verification

- **Dify API 联通**：用 curl 调用 `chat-messages` API，传入图片 + 文本，验证 Vision 识别和工具调用正确触发。
- **工具回调闭环**：Agent 调用 `reward.query_balance` → 外壳服务端返回余额 → Agent 自然语言告知用户。
- **截图监督管线**：前端定时发截图 → CV 判定 → 触发奖惩 Workflow → Agent 主动安慰，端到端 < 5秒。
- **跨平台**：分别在桌面 Chrome、Android Chrome、iPad Chrome 测试摄像头权限、屏幕共享降级、响应式布局。
- **PWA**：手机 Chrome 添加到主屏幕后可离线加载壳页、重连后恢复 session。

### Decisions

- **Dify Chatflow 而非纯 Agent 应用**：Chatflow 支持 `conversation_id` 多轮延续 + Conversation Variables 做 session 内状态管理，比单纯 Agent 模式更灵活。
- **工具实现为 HTTP 回调而非 Dify 内置逻辑**：所有业务状态（账本、画像、计时）在外壳服务端维护，Dify 工具只做 HTTP 调用，保证关注点分离——Dify 管 AI，服务端管业务。
- **奖惩判定用独立 Workflow**：与主 Chatflow 解耦，由外壳服务端的 CV 管线触发，避免 Agent 对话流被阻塞。
- **React + Vite + PWA**：一套代码覆盖桌面/平板/手机，不需要 Electron 包装（MVP阶段），通过 PWA 获得类原生体验。
- **手机端自动降级为传统模式**：因 Chrome Mobile 不支持 `getDisplayMedia`，前端自动检测能力并隐藏电子学习模式入口。

---

## Plan: 拟人化 Agent — Live2D + 语音交互层设计（v4 增量 DRAFT）

**TL;DR** — 在 Dify + 外壳服务端架构的基础上，增加三个关键能力层：①前端 Live2D 渲染（Cubism SDK WebGL + 口型同步 + 表情/动作驱动）、②前端 VAD（Silero ONNX 浏览器端语音检测）、③后端 ASR+TTS 管线。所有 Agent 交互默认走语音通道，同时保留文本输入框。用户看到的是一个会说话、有表情、有口型动作的虚拟伴侣。

---

### 一、整体交互链路

```
用户说话
  → 麦克风(getUserMedia) → 前端VAD(Silero ONNX) → 检测语音段
    → Float32音频分片 → WS发送外壳服务端
      → 外壳服务端 → 后端ASR(语音转文字)
        → 拼接截图(如有) → 调用 Dify chat-messages API
          → Dify Agent 推理 + 工具调用
          → 流式返回文本
        → 后端TTS(文字转语音, WAV)
          → 句切分 + 表情标签提取
          → WS推送前端：{audio: base64, actions: {expressions}, display_text}
      → 前端播放：
        1. Live2D setExpression(表情)
        2. startRandomMotion("Talk")
        3. wavFileHandler.start(audioData) → RMS驱动口型同步
        4. 字幕显示 display_text
        5. HTML5 Audio 播放语音
  → 播放完毕 → 恢复麦克风监听

用户打字（备选）
  → 文本框输入 → WS发送 {type:"text-input", text, images}
    → 后续流程同上（跳过ASR）
```

---

### 二、前端 Live2D 实现方案

#### 1. 渲染技术栈

| 组件 | 选型 | 说明 |
|---|---|---|
| **核心运行时** | `live2dcubismcore.min.js` (Cubism Core WASM) | Live2D 官方 SDK，必须项 |
| **框架层** | Cubism SDK for Web (Framework JS) | 模型加载、物理、表情、动作、口型同步的完整框架 |
| **集成方式** | 自定义 React Hook 封装 | `useLive2D`、`useLive2DExpression`、`useLive2DAudio` |
| **渲染上下文** | WebGL2 Canvas | Cubism SDK 原生渲染，不依赖 PixiJS |

> **参考但不照搬** Open-LLM-VTuber 的实现：它将整个 Cubism Framework 打包进了 main.js（约数千行），我们应将 Cubism SDK 的 Framework 目录作为独立模块管理，方便维护和升级。

#### 2. 模型与表情映射

在外壳服务端维护一个类似 model_dict.json 的模型注册表：

```json
{
  "name": "study_buddy",
  "url": "/live2d-models/study_buddy/runtime/model.model3.json",
  "kScale": 0.5,
  "emotionMap": {
    "neutral": 0,
    "happy": 1,
    "encouraging": 2,
    "concerned": 3,
    "disappointed": 4,
    "proud": 5,
    "playful": 6,
    "serious": 7
  },
  "idleMotionGroup": "Idle",
  "talkMotionGroup": "Talk",
  "tapMotions": {
    "HitAreaHead": {"motion": "pat", "expression": "happy"}
  }
}
```

- **表情设计侧重监督场景**：`encouraging`（鼓励完成目标）、`concerned`（发现分心时关切）、`disappointed`（反复违规）、`proud`（达成里程碑）、`playful`（讨价还价时）。
- Dify 系统提示中指导 Agent 在回复中插入 `[expression_name]` 标签。

#### 3. 口型同步

沿用 Open-LLM-VTuber 验证过的方案 — **WAV RMS 音量驱动**：

- 后端 TTS 输出 WAV 格式
- 前端 `WavFileHandler` 解析 PCM 数据，逐帧计算 RMS → 驱动模型 `ParamMouthOpenY`
- 放大系数可调（默认 2x），确保口型明显
- 不使用 viseme（音素级），因为成本高且对中文支持不成熟

#### 4. 动作系统

| 触发场景 | 动作 |
|---|---|
| 待机（idle） | 循环播放 Idle 组动作 |
| 说话中 | 随机播放 Talk 组动作 |
| 用户点击头部 | pat 动作 + happy 表情 |
| 用户完成目标 | celebrate 特殊动作 |
| 检测到分心 | alert 动作 + concerned 表情 |

#### 5. 响应式布局

| 桌面 | 平板 | 手机 |
|---|---|---|
| Live2D 占右侧 30-40% 面积，对话在左 | Live2D 居中上方，对话在下 | Live2D 小窗浮动在角落，可展开/收起 |

Canvas 使用 `ResizeObserver` 动态适配容器尺寸。专注模式下 Live2D 可最小化为小头像。

---

### 三、语音交互实现方案

#### 6. 前端 VAD（语音活动检测）

| 方面 | 方案 |
|---|---|
| **库** | `@ricky0123/vad-web` |
| **模型** | Silero VAD v5 ONNX（~2MB），通过 AudioWorklet 运行 |
| **运行环境** | 完全浏览器端，不依赖后端 |
| **音频参数** | 16kHz 采样率，单声道，回声消除 + 自动增益 + 噪声抑制 |
| **分段策略** | `positiveSpeechThreshold=0.5`，`negativeSpeechThreshold=0.35`，`redemptionFrames=8` |

流程：
- VAD 检测到 `SpeechEnd` → 获得 `Float32Array` 语音段
- 分片（每片 4096 float）→ WS JSON 发送 `{type:"mic-audio-data", audio:[...]}`
- 全部发完 → 发送 `{type:"mic-audio-end", images:[...]}` 附带截图

#### 7. 后端 ASR（语音识别）

在外壳服务端实现，与 Dify 无关（Dify 只收文本）：

| 选项 | 推荐场景 | 优势 |
|---|---|---|
| **SenseVoice（sherpa-onnx）** | 默认 / 中英混合 | 本地运行、低延迟、中文效果好、模型项目已有 |
| **Whisper API（OpenAI/Groq）** | 云端部署、不想管本地模型 | 精度高、零运维 |
| **FunASR** | 高精度中文需求 | 流式支持好 |

推荐 MVP 阶段用 **Groq Whisper API**（免费额度大、延迟低），后续切本地 SenseVoice。外壳服务端的 ASR 模块做成可插拔工厂。

#### 8. 后端 TTS（语音合成）

| 选项 | 推荐场景 | 优势 |
|---|---|---|
| **edge-tts** | MVP 首选 | 免费、中文自然、延迟可接受 |
| **Kokoro** | 需要更有个性的声音 | 本地运行、声音质感好、项目已有模型文件 |
| **OpenAI TTS** | 追求极致自然度 | 效果最好但有成本 |

**句切分 + 流式合成**（参考 Open-LLM-VTuber 的 tts_manager.py）：
1. Dify 流式返回文本 → 按句号/问号/感叹号切分
2. 每个句子独立做 TTS → 生成 WAV
3. 提取句子中的 `[expression]` 标签 → 映射为表情
4. 打包 `{type:"audio", audio: base64WAV, actions:{expressions}, display_text}` 推送前端
5. 前端按队列顺序播放 → 实现说到哪、表情变到哪

#### 9. 前端音频播放 + 同步

```
audioTaskQueue (FIFO)
  ├─ task1: {audio, expression, motion, text}
  │   → setExpression("encouraging")
  │   → startRandomMotion("Talk")
  │   → wavFileHandler.start(audioData)  // 口型同步
  │   → new Audio(dataUrl).play()        // 语音播放
  │   → 显示字幕 text
  │   → 等待 audio.ended
  ├─ task2: ...
  └─ task3: ...
→ 全部播放完 → 发送 "frontend-playback-complete" → 恢复 VAD 监听
```

#### 10. 中断逻辑

用户在 Agent 说话时开口：
- 前端 VAD 检测到新语音 → 立即发送 `{type:"interrupt-signal", text: "已播放的文本"}`
- 前端：停止当前音频播放、清空队列、Live2D 回到 Idle
- 后端：取消当前 TTS 任务、Agent 记忆添加中断标记
- 体验：类人的「打断对方说话」效果

---

### 四、Dify 侧的适配

#### 11. 系统提示新增指令

在 Dify Chatflow 的 Instruction 中新增如下提示词模块：

```
## 表情控制
在你的回复中插入表情标签来控制你的虚拟形象。可用表情：
[neutral] [happy] [encouraging] [concerned] [disappointed] [proud] [playful] [serious]
在每句话前插入一个最匹配当前情感的表情标签。例如：
"[happy] 太好了，你今天的目标完成了！[proud] 我真的很为你骄傲。"

## 口语化
你的回复将通过语音合成播放。请：
- 使用口语化表达，避免书面语
- 适当使用语气词（嗯、啊、呢、吧）
- 数字和日期用口语方式说出
- 每段回复控制在 2-3 句以内，保持对话节奏
- 不要使用 emoji、特殊符号或 markdown 格式
```

#### 12. 文件输入适配

Dify `chat-messages` API 支持通过 `files` 参数传入图片：
- 外壳服务端收到前端截图 → base64 解码 → 临时保存或转为 URL
- 调用 Dify API 时通过 `files: [{type:"image", transfer_method:"local_file", upload_file_id:"..."}]` 传入
- 或使用 `transfer_method:"remote_url"` 传可访问的临时 URL
- Dify LLM 节点需开启 Vision 功能

---

### 五、外壳服务端新增模块

#### 13. 音频处理管线

```python
# 伪代码结构
class AudioPipeline:
    asr: ASRFactory.create(config.asr_provider)   # 可插拔 ASR
    tts: TTSFactory.create(config.tts_provider)   # 可插拔 TTS

    async def process_voice_input(self, audio_chunks, images) -> str:
        """音频分片 → 拼接 → ASR → 文本"""
        raw = np.concatenate(audio_chunks).astype(np.float32)
        text = await self.asr.transcribe(raw, sample_rate=16000)
        return text

    async def stream_tts(self, text_stream, ws):
        """文本流 → 句切分 → 表情提取 → TTS → WS推送"""
        async for sentence, expression in split_and_extract(text_stream):
            wav_bytes = await self.tts.synthesize(sentence)
            audio_b64 = base64.b64encode(wav_bytes).decode()
            await ws.send_json({
                "type": "audio",
                "audio": audio_b64,
                "actions": {"expressions": [expression]},
                "display_text": {"text": sentence}
            })
```

#### 14. 表情标签提取器

从 Dify 返回的文本中提取并清除 `[expression]` 标签：

```python
import re

def extract_expressions(text: str) -> tuple[str, list[str]]:
    expressions = re.findall(r'\[(\w+)\]', text)
    clean_text = re.sub(r'\[\w+\]\s*', '', text)
    return clean_text, expressions
```

---

### 六、前端组件结构

```
src/
├── components/
│   ├── Live2DCanvas/
│   │   ├── Live2DCanvas.tsx       # WebGL Canvas + Cubism 初始化
│   │   ├── useLive2D.ts           # 模型加载/销毁 Hook
│   │   ├── useLive2DExpression.ts  # 表情控制 Hook
│   │   ├── useLive2DAudio.ts      # 口型同步 + 动作 Hook
│   │   └── WavFileHandler.ts      # RMS 口型同步处理器
│   ├── VoiceInput/
│   │   ├── VoiceInput.tsx         # 麦克风按钮 + 状态指示
│   │   ├── useVAD.ts              # Silero VAD Hook
│   │   └── useAudioSender.ts     # 音频分片 + WS发送
│   ├── ChatPanel/
│   │   ├── ChatPanel.tsx          # 对话面板（字幕 + 文本输入框）
│   │   ├── MessageBubble.tsx      # 消息气泡
│   │   └── TextInput.tsx          # 文本输入框（保留）
│   ├── AudioPlayer/
│   │   ├── AudioPlayer.tsx        # 音频队列播放器
│   │   └── useAudioQueue.ts      # 播放队列管理 Hook
│   └── SupervisionPanel/
│       ├── StatusBar.tsx          # 状态栏（计时器、余额、任务）
│       └── CameraPreview.tsx     # 摄像头预览（环境校准时显示）
├── hooks/
│   ├── useWebSocket.ts           # WS连接管理 + 重连
│   └── useSupervision.ts         # 监督状态管理
├── libs/
│   ├── live2dcubismcore.min.js
│   ├── silero_vad_v5.onnx
│   └── vad.worklet.bundle.min.js
└── live2d-models/
    └── study_buddy/runtime/...
```

---

### 七、关键体验细节

| 场景 | 效果 |
|---|---|
| **待机** | Live2D Idle动作循环 + 眨眼，用户感受到"活着的" |
| **用户说话时** | 麦克风指示灯亮起，Live2D 微微侧头（Listening 动作） |
| **Agent 回复** | 口型随语音同步张合，表情随情感切换，说话动作自然 |
| **用户打断** | 立即停止说话和口型，保持准备倾听状态 |
| **检测到分心** | Agent 主动开口（concerned 表情）→ 温和提醒 |
| **完成目标** | Agent 开心（proud 表情 + celebrate 动作）→ 「太棒了！」 |
| **讨价还价时** | playful 表情 → 像朋友一样商量 |
| **用户点击头部** | 摸头反应（pat动作 + happy表情），增强互动感 |
| **空闲较久** | Agent 主动轻声搭话（proactive speak），不让气氛冷掉 |

---

### Verification

- **口型同步精度**：多段中/英文 TTS 输出测试，确认 RMS 驱动的口型开合与语音节奏匹配。
- **VAD 灵敏度**：安静/嘈杂环境下测试，确认不会误触发或漏检。
- **中断响应**：Agent 说话时用户开口，< 300ms 内停止播放并开始听。
- **流式体验**：从用户说完话到 Agent 开始说话（首字延迟），桌面端目标 < 2秒。
- **跨平台 Live2D**：桌面/平板/手机 Chrome 上 WebGL2 渲染正常，Canvas 尺寸自适应。
- **文本输入兼容**：切换到文本模式时，TTS 仍然播放，Live2D 仍然驱动。

### Decisions

- **VAD 在前端执行**：避免音频全量上传的带宽与延迟开销。Silero ONNX 模型仅 ~2MB，AudioWorklet 在主流 Chrome 版本均支持。
- **ASR/TTS 在外壳服务端执行而非 Dify**：Dify 原生不支持语音 I/O。外壳服务端做 ASR→文本→调Dify→文本→TTS 的转换。
- **口型用 RMS 而非 viseme**：RMS 方案简单可靠、跨语言通用。viseme 对中文支持差且复杂度高，ROI 不值。
- **表情标签嵌入文本流**：与 Open-LLM-VTuber 同样思路，在 Dify 提示词中指导 Agent 插入 `[expression]` 标签，外壳服务端提取后下发前端，零额外 API 调用。
- **保留文本输入框**：作为语音的补充通道——教室/图书馆等不方便说话的场景，或者用户想精确输入（如修改学习计划）。



  

了解了你们的完整计划。现在针对一个 3-4 人、大一大二、无 Git 协作经验、重度依赖 vibe coding 的团队，给出务实的分工与协作方案。

---

## Plan: 团队分工与协作流程（DRAFT）

**TL;DR** — 按**模块边界**分工，而非按前后端分。你们的系统天然由 WebSocket 和 HTTP API 解耦为 4 个独立模块，每人独占一个模块，通过**先约定接口 → 再各自实现 → 最后联调**的节奏并行开发。Git 协作从最简规则开始——每人一个分支，合进 `main` 前找另一个人看一眼。

---

### 一、分工方案（3-4 人）

| 角色 | 负责模块 | 核心产出 | 技术栈 |
|---|---|---|---|
| **A — 前端** | Web App 全部 | React 页面、Live2D 渲染、VAD 语音采集、WS 通信、摄像头/屏幕截图、UI 交互 | React + TS + Vite + TailwindCSS + Cubism SDK |
| **B — 外壳服务端** | WS 网关 + ASR/TTS 管线 + Dify 代理层 | 音频处理、调用 Dify API、流式转发、表情提取、会话生命周期管理 | Python + FastAPI + WebSocket |
| **C — 业务服务** | 奖惩系统 + 用户系统 + 画像/记忆 + 计时器 + 数据库 | REST API（供 Dify 工具回调）、账本、审计日志、向量检索、用户认证 | Python + FastAPI + SQLite/PostgreSQL + ChromaDB |
| **D — Dify + CV** | Dify 配置 + 监督判定管线 | Chatflow 编排、Workflow 编排、工具插件注册、提示词设计、CV 人脸/注意力检测模型集成 | Dify 平台 + Python + MediaPipe |

> **如果只有 3 人**：B 和 C 合并为一人（外壳服务端 + 业务服务都是 Python FastAPI，合并自然）。D 的 CV 管线工作量不大（MediaPipe 开箱即用），可由 C 兼任部分。

#### 为什么这样分而不是「前端/后端」？

- **避免后端 3 人挤在一起**：传统「前后端分离」会导致只有 1 人写前端、其余全写后端却互相踩脚。
- **模块间通过 API 合同解耦**：A 与 B 通过 WebSocket 消息协议通信，B 与 Dify 通过 HTTP API 通信，C 通过 REST API 被 Dify 工具回调。每人只需关心自己的输入/输出格式。
- **适合 vibe coding**：每个模块可以独立对 AI 描述需求，不会因为代码交织而产生冲突。

---

### 二、并行开发的关键：先定接口合同

在写任何代码之前，团队花 **半天时间** 一起定义三份「合同」：

#### 合同 1：前端 ↔ 外壳服务端（WebSocket 消息协议）

```
# 上行（前端 → 服务端）
{type: "mic-audio-data", audio: number[]}
{type: "mic-audio-end", images: [{source, data, mime_type}]}
{type: "text-input", text: string, images: [...]}
{type: "interrupt-signal", text: string}
{type: "periodic-screenshot", images: [...]}
{type: "pause-request", reason: string}
{type: "resume-request"}
{type: "frontend-playback-complete"}

# 下行（服务端 → 前端）
{type: "audio", audio: "base64", actions: {expressions: [...]}, display_text: {text, name}}
{type: "agent-text-chunk", text: string}     # 流式文字
{type: "supervision-alert", message: string, severity: "soft"|"hard"}
{type: "supervision-state-change", state: "setup"|"active"|"paused"|"completed"}
{type: "balance-update", balance: number, change: number, reason: string}
{type: "model-info", model_info: {...}}
{type: "control", command: string}
```

#### 合同 2：Dify 工具 → 业务服务端（REST API）

```
GET  /api/reward/balance/{user_id}
POST /api/reward/event  {user_id, type, amount, reason, evidence_id}
POST /api/supervision/pause  {user_id, duration, reason}
POST /api/supervision/resume  {user_id}
GET  /api/profile/{user_id}
PATCH /api/profile/{user_id}  {field, value}
POST /api/memory/search  {user_id, query, top_k}
GET  /api/plan/today/{user_id}
PUT  /api/plan/{user_id}  {tasks: [...]}
GET  /api/timer/status/{user_id}
POST /api/session/summarize  {user_id, session_id, messages: [...]}
```

#### 合同 3：外壳服务端 ↔ Dify（Dify Chat API 调用格式）

这个不用自己定——Dify 的 `POST /v1/chat-messages` API 格式是固定的，B 只需按照 Dify 文档封装调用即可。

> **合同定好后，每人可以用 mock 数据独立开发和测试。** A 可以用假的 WS 服务端回放录好的消息测 UI；B 可以用假的 Dify 响应测管线；C 可以用 Postman 测 API。

---

### 三、Git 协作最简规则

你们不需要复杂的 Git Flow。以下 5 条规则够用：

#### 规则 1：仓库结构

```
study-buddy/
├── frontend/          ← A 的领地
├── server/            ← B 的领地
│   ├── gateway/       ← WS 网关 + ASR/TTS
│   └── services/      ← C 的领地（奖惩/用户/记忆等）
├── dify/              ← D 的领地（导出的 DSL、提示词文本、工具插件代码）
├── cv/                ← D 的领地（监督判定管线）
├── docs/              ← 接口合同、设计文档
│   ├── ws-protocol.md
│   └── api-contract.md
├── docker-compose.yml
└── README.md
```

> **关键：每人有自己的目录，互不侵入。** 这从物理结构上避免了合并冲突。

#### 规则 2：分支策略

```
main          ← 永远可运行的版本
├── feat/frontend-xxx    ← A 的功能分支
├── feat/server-xxx      ← B 的功能分支
├── feat/services-xxx    ← C 的功能分支
└── feat/dify-xxx        ← D 的功能分支
```

- 每个功能用 `feat/你的模块-简短描述` 命名分支
- 完成后发 **Pull Request** 到 `main`
- 找**另一个人**点 Approve（不需要逐行 review，看一眼跑不跑得通就行）
- Approve 后自己 merge

#### 规则 3：提交习惯

```bash
# 每完成一个小功能就 commit，不要攒一大堆
git add .
git commit -m "feat(frontend): 完成 Live2D 模型加载"
git commit -m "fix(server): 修复 ASR 音频拼接 bug"
git commit -m "feat(services): 实现奖惩余额查询 API"
```

#### 规则 4：冲突预防

- **不改别人目录里的文件**。如果需要改，先在群里说一声。
- 共享文件（如 `docker-compose.yml`、`docs/`）改动前也说一声。
- 每天开始工作前 `git pull origin main`。

#### 规则 5：如果出了冲突

不要慌。找**被冲突的那个人**一起在 VS Code 里用冲突编辑器解决。90% 的冲突因为改了同一个文件，按规则 4 几乎不会发生。

---

### 四、开发阶段与里程碑

#### Phase 0：基建（第 1-2 天，全员一起）

- [ ] 创建 GitHub 仓库，初始化目录结构
- [ ] 每人 clone 仓库，练习一次完整的 branch → commit → PR → merge 流程
- [ ] 一起写完接口合同（`docs/ws-protocol.md` + `docs/api-contract.md`）
- [ ] 部署 Dify（Docker Compose 一键拉起）
- [ ] 统一开发环境：Node.js 版本、Python 版本、包管理器

#### Phase 1：骨架联通（第 3-7 天，各自并行）

目标：**最小闭环** — 用户打字 → Agent 文字回复 → 显示在屏幕上

| 人 | 任务 | 验收标准 |
|---|---|---|
| A | React 项目脚手架 + 文本输入框 + WS 连接 + 消息显示 | 能连 WS，发文字，显示回复 |
| B | FastAPI + WS 端点 + 调用 Dify chat-messages API + 流式转发 | curl 发消息能收到 Dify 回复 |
| C | FastAPI + 用户注册/登录 API + SQLite 数据库初始化 | Postman 测试通过 |
| D | Dify Chatflow 创建 + 基础人设提示词 + 测试对话 | Dify 调试界面对话正常 |

**Phase 1 结束时联调**：A↔B 连通（前端发文字→服务端→Dify→回复显示在前端）。

#### Phase 2：语音 + Live2D（第 8-14 天）

| 人 | 任务 |
|---|---|
| A | VAD 集成 + 麦克风采集 + 音频播放队列 + Live2D Canvas + 口型同步 |
| B | ASR 集成（Groq Whisper）+ TTS 集成（edge-tts）+ 表情标签提取 + 音频 base64 打包 |
| C | 奖惩系统 API + 账本数据库 + 用户画像 CRUD |
| D | Dify 工具插件开发（reward/profile/plan）+ 添加表情标签指令到提示词 |

**Phase 2 结束时联调**：用户能用语音和 Agent 对话，Live2D 有口型和表情。

#### Phase 3：监督核心（第 15-21 天）

| 人 | 任务 |
|---|---|
| A | 摄像头/屏幕截图定时发送 + 监督状态 UI + 暂停/恢复交互 + 番茄钟界面 |
| B | 截图路由到 CV 管线 + 监督事件→Agent主动对话触发 + 暂停/恢复状态管理 |
| C | 计时器服务 + 服务费计费 + 审计日志 + Session 摘要管线 |
| D | CV 人脸检测（MediaPipe）+ 奖惩判定 Workflow + 环境引导提示词 |

**Phase 3 结束时联调**：完整监督闭环可运行。

#### Phase 4：打磨 + Demo（第 22-28 天）

- 全员一起做端到端测试、修 bug
- UI 美化、动画打磨
- 准备 Demo 视频/演示文稿
- 压力测试、边界情况处理

---

### 五、Vibe Coding 最佳实践

由于你们会大量用 AI 辅助编程，以下建议能让效率翻倍：

1. **每人给 AI 一份自己模块的"上下文简报"** — 把接口合同 + 模块职责 + 技术栈写成一个 `CLAUDE.md` 或 `INSTRUCTIONS.md` 放在自己目录根下。每次开新对话时让 AI 先读这个文件。

2. **让 AI 先生成接口 stub，再填充实现** — 例如 C 可以先让 AI 把所有 REST API 的路由骨架生成出来（只有函数签名 + 返回 mock 数据），确认结构正确后再逐个实现。

3. **不要让 AI 一次性生成整个模块** — 分成小任务：「先帮我实现 WebSocket 连接和重连逻辑」「再帮我加上 VAD 语音检测」。每个小任务完成后 commit。

4. **复制粘贴接口合同给 AI** — 当 A 和 B 各自让 AI 写代码时，把 `ws-protocol.md` 贴给 AI，AI 生成的前后端消息格式自然一致。这就是合同的价值。

5. **遇到 bug 先让 AI 诊断** — 把错误日志、相关代码贴给 AI，通常能直接修复，不用自己从头排查。

---

### Verification

- **Phase 0 验收**：每人都成功完成过一次 PR → Merge，接口合同文档存在且各方认同。
- **Phase 1 验收**：在一台电脑上 `docker-compose up` 后，浏览器打开能文字对话。
- **Phase 2 验收**：对着麦克风说话 → Agent 语音回复 → Live2D 嘴型同步。
- **Phase 3 验收**：开启监督 → 离开摄像头画面 → Agent 提醒 → 余额扣减 → 可在 UI 看到记录。

### Decisions

- **按模块分工而非按层** — 每人拥有完整的纵向责任，减少跨人依赖和沟通成本。
- **目录物理隔离** — 从仓库结构上杜绝 90% 的 Git 冲突。
- **接口合同先行** — 使并行开发成为可能，也让 vibe coding 时前后端 AI 生成的代码天然兼容。
- **Phase 渐进式** — 每个 Phase 都有可运行的端到端闭环，避免到最后才发现联不通。


有没有可能不从头开发，适当使用open-LLM-Vtuber的代码，但是避免直接套壳？

可以，而且这是你们当前最稳妥的路线：**“借基础设施，重做产品层”**，就不算套壳。  
法律上也可行：仓库主体是 MIT（见 LICENSE），但 Live2D 示例模型有单独条款（见 LICENSE-Live2D.md），建议你们用自有模型或确认授权。

**建议复用（高价值、低“套壳感”）**
- 语音与多模态底座：WS 音频协议、ASR/TTS/VAD 工厂思想、流式编排思路。
- Live2D 技术链：模型加载、表情映射、口型同步机制（技术可借，角色与交互重做）。
- 工具调用框架思路：MCP/工具状态回传模式。

**必须重做（决定你们是“新产品”）**
- 核心业务闭环：监督判定、奖惩账本、暂停协商、服务费计时、申诉复核。
- 产品信息架构与前端交互：页面结构、学习流程、状态机、可视化面板。
- Agent 人设与策略：提示词体系、情感逻辑、长期记忆策略。
- 数据模型与审计：用户/会话/证据/事件/交易表设计。

**避免“套壳”的硬标准（答辩可直接用）**
- 代码复用比例控制在底层模块，核心业务代码 100% 自研。
- UI/交互流程与原项目明显不同（不是“聊天桌宠”，而是“学习监督系统”）。
- 独立部署拓扑：Dify + 外壳服务端 + 业务服务端，而非原仓库一体化结构。
- 有你们独有指标：专注率、误判率、协商通过率、净奖励等。


**可以复用白名单（建议优先借）**
- 协议/编排思路： websocket_handler.py、conversation_utils.py、stream_audio.py
- 可插拔工厂模式： asr_factory.py、tts_factory.py、vad_factory.py
- 多模态输入结构： input_types.py
- 工具调用框架： tool_adapter.py、tool_executor.py、mcp_client.py
- 配置组织方式（不是配置内容）： conf.default.yaml、config_manager

**灰名单（可参考实现，但建议重写）**
- 会话执行器： single_conversation.py、conversation_handler.py
- 提示词装配： prompt_loader.py、service_context.py
- 路由结构： routes.py

**黑名单（不要直接搬，避免套壳/版权风险）**
- 角色与人设内容： characters、prompts
- 前端成品包： main-nu7uwxNJ.js（编译产物，禁止照搬）
- Live2D 示例角色资源： live2d-models（受单独条款约束，见 LICENSE-Live2D.md）
- 现成历史数据与素材： chat_history、avatars、backgrounds

**落地规则（团队执行）**
- 只“借设计和抽象”，不整文件复制；复用代码必须保留 MIT 许可声明（见 LICENSE）。
- 你们项目核心模块必须 100% 自研：监督判定、奖惩账本、协商暂停、服务费计时、审计申诉、长期记忆。
- 对外展示时明确“基于开源组件二次开发”，并说明新增模块与指标，形成非套壳证据链。

要的话我可以下一步直接给你们做一份“3-4人任务到目录级别”的分配清单（谁负责哪个文件夹和接口）。

---

## 2026-03-06 迁移收尾记录（WebSDK 渲染链路）

### 已完成

- Live2D 渲染链路切换为 `frontend/src/live2d/WebSDK`（以 Open-LLM-VTuber WebSDK 结构为基础）。
- `Live2DCanvas` 完成运行时惰性加载，避免模块初始化异常导致整页黑屏。
- 修复 ESM 运行时错误：将 Framework 内大量“类型导出”改为 `import type`，消除浏览器 `does not provide an export named ...` 报错。
- 修复浏览器端 `require is not defined`：改为 ESM `import`。
- 日志分级：WebSDK 初始化日志与调试浮层仅在开发环境显示，生产环境静默。

### 仓库整理

- 删除根目录旧链路遗留：`Core/`、`live2dcubismcore.min.js`、`CubismWebFramework/`。
- 保留并使用前端静态资源：`frontend/public/lib/live2dcubismcore.min.js`。
- 当前唯一生效渲染实现：`frontend/src/components/Live2DCanvas/Live2DCanvas.tsx` + `frontend/src/live2d/WebSDK/**`。

### 说明

- 以上收尾后的运行方式为：
  1. `frontend/index.html` 注入 Cubism Core 脚本；
  2. 前端通过 WebSocket 接收 `model-info/audio` 等消息；
  3. WebSDK 负责模型加载、动作/表情、音频联动。
