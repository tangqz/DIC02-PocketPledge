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

- Base URL 必须是 Dify 服务器可达的地址，不能写 `127.0.0.1` 或 `localhost`
- 当前这套联调环境已验证可达的地址是 `http://dify.qizhi7z.com`
- 调试期可使用公开隧道或反向代理，例如 Cloudflare Tunnel、ngrok、frp、SSH reverse tunnel
- 如果你和 Dify 服务器在同一私网/VPN，也可以填写该私网可达地址
- 认证方式使用 HTTP Bearer
- 工具调用时显式传入 `user_id`，不要依赖“当前登录用户”语义
- 工具重试只给读取类接口开启，写入类接口最多 1 到 2 次，避免重复写摘要或暂停记录

联调原则：

- Dify 自定义工具是从 Dify 所在服务器发起 HTTP 请求，不是从你的浏览器或本地开发机发起
- 因此 `127.0.0.1:12393` 只会指向 Dify 服务器自身，不会指向你本地正在运行的 FastAPI
- 最稳妥的调试办法，是先把本地后端通过隧道暴露成一个临时公网地址，再把该地址填进工具 Base URL
- 如果暂时没有 TLS 证书，也可以先用 HTTP 调试；但此时 Dify 工具里也要填 HTTP 地址，不能强行写 HTTPS

工具分组建议：

- 读接口：`getUserStatus` `getUserPlan` `getUserProfile` `listUserPauseRequests` `listUserSessionSummaries` `listUserTransactions`
- 写接口：`updateUserPlan` `updateUserProfile` `recordUserPauseRequest` `createUserSessionSummary`

规范参考：

- Swagger / OpenAPI Specification 3.0.3 compatible subset: https://swagger.io/specification/
