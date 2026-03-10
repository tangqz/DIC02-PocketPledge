# Dify Workflows

本目录存放 Study Buddy 的正式 Dify 编排归档版本。

文件说明：
- white_brain.chat.yml: 白脑聊天 Agent，负责口语化陪伴与系统事件转译
- black_brain.workflow.yml: 黑脑视觉判定 Workflow，负责输出结构化走神判定
- system_agent.workflow.yml: 系统 Agent 编排 Workflow，负责把用户意图翻译成结构化工具指令
- ../personas/default_study_buddy.yaml: 默认角色资料卡，结构参考 Open-LLM-VTuber 的 character_config
- ../schemas/persona_card.schema.json: 人设资料卡 schema

当前策略：
- 仓库中的这些文件作为可导入 Dify 的源归档
- 运行时后端优先使用本地 system agent 编排与 Dify Chat/Workflow API 代理
- 当 Dify 工作流尚未上线或不可用时，系统 Agent 本地逻辑继续兜底
