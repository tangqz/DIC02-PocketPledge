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
- 目前未加管理员鉴权

## 已缺失能力

以下能力尚无对应 REST 工具接口，系统 Agent 目前无法通过标准工具调用完成：

- 用户画像文档读取/更新
- RAG 检索与记忆写回
- 暂停申请历史查询
- 暂停审批结果持久化
- 学习计划创建、调整、查询、删除
- 日历型计划展示数据接口
- 奖励任务创建、完成确认、奖励发放
- 会话总结持久化
- Reward Pool 向用户返奖的正式接口
- Charity / Pool / 用户流水查询接口
