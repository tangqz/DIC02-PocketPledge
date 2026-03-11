# Dify Custom Tools

本目录提供给 Dify 导入的自定义工具 OpenAPI 归档。

当前文件：

- [dify_orchestration/tools/study_buddy_custom_tools.openapi.yaml](dify_orchestration/tools/study_buddy_custom_tools.openapi.yaml)

导入方式：

1. 在 Dify 的 Tools 页面选择导入 OpenAPI/Swagger。
2. 导入 [dify_orchestration/tools/study_buddy_custom_tools.openapi.yaml](dify_orchestration/tools/study_buddy_custom_tools.openapi.yaml)。
3. 在工具认证里配置 Bearer Token。
4. Bearer Token 使用后端环境变量 `DIFY_TOOL_BEARER_TOKEN` 的固定值，不要使用普通用户 JWT。
5. 导入后按需开启重试与失败分支。

建议的 Dify 配置：

- Base URL 指向你的后端，例如 `http://1.15.77.110:12393`
- 认证方式使用 HTTP Bearer
- 工具调用时显式传入 `user_id`，不要依赖“当前登录用户”语义
- 工具重试只给读取类接口开启，写入类接口最多 1 到 2 次，避免重复写摘要或暂停记录

工具分组建议：

- 读接口：`getUserStatus` `getUserPlan` `getUserProfile` `listUserPauseRequests` `listUserSessionSummaries` `listUserTransactions`
- 写接口：`updateUserPlan` `updateUserProfile` `recordUserPauseRequest` `createUserSessionSummary`

规范参考：

- Swagger / OpenAPI Specification 3.1.1: https://swagger.io/specification/
