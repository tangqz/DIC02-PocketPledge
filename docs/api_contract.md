# Study Buddy API Contract

本文档描述当前后端已经实现的 REST 接口，以及与产品描述相比仍然缺失的能力。

## Base

- 默认本地基址: http://localhost:12393
- 认证方式: Authorization: Bearer <JWT>

## Auth

### POST /api/auth/register

请求体:

```json
{
	"username": "alice",
	"password": "secret123",
	"email": "alice@example.com"
}
```

返回:

```json
{
	"access_token": "...",
	"token_type": "bearer",
	"user_id": 3,
	"username": "alice"
}
```

### POST /api/auth/login

请求体:

```json
{
	"username": "alice",
	"password": "secret123"
}
```

### GET /api/auth/me

返回当前用户与钱包余额。

## Business

### POST /api/business/session/start

说明:
- 需要 JWT
- 当前实现会立即执行预扣费
- 扣费金额 = planned_focus_minutes * 15

请求体:

```json
{
	"planned_focus_minutes": 25
}
```

返回字段:
- upfront_cost
- balance_after
- pool_balance_after
- session_ref
- tx_id

### POST /api/business/penalty/execute

说明:
- 需要 JWT
- 当前实现会把罚金拆分到 charity_sink 和 reward_pool

请求体:

```json
{
	"reason": "检测到连续走神",
	"distraction_count": 1
}
```

### GET /api/business/me/status

返回当前用户余额与是否破产。

### GET /api/business/users/{user_id}/status

说明:
- 当前为内部接口，保留给 Dify/tool callback 使用
- 需要固定 Bearer Token，来自后端环境变量 `DIFY_TOOL_BEARER_TOKEN`

## 已缺失能力

以下能力现已具备最小后端接口，可供系统 Agent 或 Dify 工具调用：

- `GET /api/business/me/plan`：读取当前有效学习计划
- `PUT /api/business/me/plan`：创建或更新当前学习计划
- `GET /api/business/me/profile`：读取有限长度用户画像文档
- `PUT /api/business/me/profile`：更新用户画像文档
- `GET /api/business/me/pause-requests`：查询暂停申请历史
- `POST /api/business/me/pause-requests`：写入一次暂停审批结果
- `GET /api/business/me/session-summaries`：查询历史会话总结
- `POST /api/business/me/session-summaries`：写入一条会话总结
- `GET /api/business/me/transactions`：查询当前用户相关流水

以下能力现已具备固定 Bearer + `user_id` 显式传参的内部接口，更适合 Dify 工具调用：

- `GET /api/business/users/{user_id}/status`
- `GET /api/business/internal/users/{user_id}/plan`
- `PUT /api/business/internal/users/{user_id}/plan`
- `GET /api/business/internal/users/{user_id}/profile`
- `PUT /api/business/internal/users/{user_id}/profile`
- `GET /api/business/internal/users/{user_id}/pause-requests`
- `POST /api/business/internal/users/{user_id}/pause-requests`
- `GET /api/business/internal/users/{user_id}/session-summaries`
- `POST /api/business/internal/users/{user_id}/session-summaries`
- `GET /api/business/internal/users/{user_id}/transactions`

以下能力仍未实现完整产品闭环：

- RAG 检索与记忆写回的自动编排
- 日历型计划展示与周期性计划规则引擎
- 奖励任务创建、完成确认、奖励发放
- Reward Pool 向用户返奖的正式接口
- Charity / Pool 的独立管理接口
