# Dify Workflows

本目录存放 Study Buddy 的正式 Dify 编排归档版本。

文件说明：
- chatbot.yml: 白脑聊天应用，负责口语化陪伴与系统事件转译
- visual-judgement.yml: 黑脑视觉判定 Workflow，负责输出结构化走神判定
- system-agent.yml: 系统 Agent 提示词与输入输出归档，当前更推荐在 Dify 中以 Agent 模式配置，用于自由调用工具
- ../personas/default_study_buddy.yaml: 默认角色资料卡，结构参考 Open-LLM-VTuber 的 character_config
- ../schemas/persona_card.schema.json: 人设资料卡 schema

当前策略：
- 仓库中的这些文件作为可导入 Dify 的源归档
- 运行时后端优先使用本地 system agent 编排与 Dify Chat/Workflow API 代理
- 当 Dify 工作流尚未上线或不可用时，系统 Agent 本地逻辑继续兜底

工作流类型建议：
- 白脑使用对话应用。当前归档里的 `mode: advanced-chat` 对应 Dify 的多轮对话应用，后端通过 `/chat-messages` 调用。
- 黑脑使用 Workflow。当前归档通过 `/workflows/run` 阻塞调用，输入为 `current_task + images`，输出结构化 JSON。
- 系统 Agent 如果需要自主决定调用哪些工具、以及按结果继续迭代，优先使用 Agent 模式而不是纯 Workflow。
- 如果你只需要稳定的结构化判定且工具链固定，才考虑 Workflow。

系统 Agent 的可视化编排建议：
- 当前更推荐直接使用 Agent 模式，并为其挂载 `getUserStatus`、`getUserPlan`、`getUserProfile`、`listUserPauseRequests`、`listUserSessionSummaries`、`listUserTransactions` 等工具。
- 选择支持函数调用的模型，并给每个工具写清楚“什么时候用、不要什么时候用”的描述。
- 把 `user_id` 作为上游输入变量传给 Agent，让 Agent 在工具调用时自动填参。
- 将最大迭代次数控制在 3 到 5，避免 pause/plan 这类轻任务过度循环。
- 如果你仍需要严格结构化输出，可让 Agent 的最终回答产出 JSON，再由后端按 JSON 解析。

手动上传到云端前后的注意事项：
- 你修改本目录中的 yml 后，仍然需要手动在 Dify 云端重新导入或覆盖对应应用，仓库修改不会自动生效。
- chatbot.yml 和 system-agent.yml 里的 knowledge-retrieval 节点当前仍保留空的 dataset_ids，需要你在云端绑定真实数据集。
- 推荐给白脑绑定的检索数据：用户画像文档、会话总结、偏好/联想性记忆。
- 推荐给系统 Agent 绑定的检索数据：用户画像文档、暂停历史、历史计划、会话总结。
- 如果你在云端给系统 Agent 注册了 HTTP 工具，请确保它们与后端当前 REST 接口一致，再重新发布。
- Dify 自定义工具的 OpenAPI 导入文件放在 [dify_orchestration/tools/study_buddy_custom_tools.openapi.yaml](dify_orchestration/tools/study_buddy_custom_tools.openapi.yaml)。

