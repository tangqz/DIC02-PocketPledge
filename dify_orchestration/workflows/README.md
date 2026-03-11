# Dify Workflows

本目录存放 Study Buddy 的正式 Dify 编排归档版本。

文件说明：
- chatbot.yml: 白脑聊天应用，负责口语化陪伴与系统事件转译
- visual-judgement.yml: 黑脑视觉判定 Workflow，负责输出结构化走神判定
- system-agent.yml: 系统 Agent Workflow，负责把用户意图翻译成结构化决策
- ../personas/default_study_buddy.yaml: 默认角色资料卡，结构参考 Open-LLM-VTuber 的 character_config
- ../schemas/persona_card.schema.json: 人设资料卡 schema

当前策略：
- 仓库中的这些文件作为可导入 Dify 的源归档
- 运行时后端优先使用本地 system agent 编排与 Dify Chat/Workflow API 代理
- 当 Dify 工作流尚未上线或不可用时，系统 Agent 本地逻辑继续兜底

工作流类型建议：
- 白脑使用对话应用。当前归档里的 `mode: advanced-chat` 对应 Dify 的多轮对话应用，后端通过 `/chat-messages` 调用。
- 黑脑使用 Workflow。当前归档通过 `/workflows/run` 阻塞调用，输入为 `current_task + images`，输出结构化 JSON。
- 系统 Agent 使用 Workflow。它需要结构化输出，后端通过 `/workflows/run` 阻塞调用。

系统 Agent 的可视化编排建议：
- 推荐在可视化界面里增加一个 Question Classifier，把请求分为 `pause`、`plan`、`session-control`、`visual-context`、`other` 五类。
- `pause` 分支挂工具：`getUserStatus`、`getUserProfile`、`listUserPauseRequests`、可选 `listUserSessionSummaries`，然后进入带 JSON Schema 的 LLM 节点。
- `plan` 分支挂工具：`getUserPlan`、`getUserProfile`、可选 `listUserSessionSummaries`，然后进入带 JSON Schema 的 LLM 节点。
- `session-control` 分支通常不需要工具，直接进入结构化 LLM 节点即可。
- `visual-context` 分支不需要工具，直接让 LLM 输出 `requires_capture=true` 与 `capture_sources`。
- 如果你想让系统 Agent 自己维护画像文档或写回总结，请在可视化界面单独加 Tools 节点调用 `updateUserProfile`、`createUserSessionSummary`，不要手写 YAML 猜字段。

手动上传到云端前后的注意事项：
- 你修改本目录中的 yml 后，仍然需要手动在 Dify 云端重新导入或覆盖对应应用，仓库修改不会自动生效。
- chatbot.yml 和 system-agent.yml 里的 knowledge-retrieval 节点当前仍保留空的 dataset_ids，需要你在云端绑定真实数据集。
- 推荐给白脑绑定的检索数据：用户画像文档、会话总结、偏好/联想性记忆。
- 推荐给系统 Agent 绑定的检索数据：用户画像文档、暂停历史、历史计划、会话总结。
- 如果你在云端给系统 Agent 注册了 HTTP 工具，请确保它们与后端当前 REST 接口一致，再重新发布。
- Dify 自定义工具的 OpenAPI 导入文件放在 [dify_orchestration/tools/study_buddy_custom_tools.openapi.yaml](dify_orchestration/tools/study_buddy_custom_tools.openapi.yaml)。

