# Study Buddy API Contract

本文档描述当前后端已经实现的 REST 接口，以及与产品描述相比仍然缺失的能力。
当前项目已完全弃用 Dify，采用本地代理（`AGENT_BACKEND=local`）架构。

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

返回:

```json
{
	"access_token": "...",
	"user_id": 3,
	"username": "alice"
}
```

### GET /api/auth/me

返回当前用户基础信息与钱包余额。

## Business

业务接口主要分为公开给前端调用的 `/api/business/me/*` 接口，和留给系统内部工具调用的 `/api/business/internal/users/{user_id}/*` 接口。内部接口仍然通过请求头中的 `Authorization: Bearer <配置的DIFY_TOOL_BEARER_TOKEN>` 进行认证保护。

### 核心操作

#### POST /api/business/session/start

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

返回包含 `upfront_cost`, `balance_after`, `pool_balance_after`, `session_ref`, `tx_id`。

#### POST /api/business/penalty/execute

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

#### POST /api/business/me/wallet/topup

说明:
- 需要 JWT
- 向钱包充值

请求体:

```json
{
	"amount": 1000,
	"reason": "测试充值"
}
```

### 状态查询

#### GET /api/business/me/status

返回当前用户余额与是否破产 (`balance`, `is_bankrupt`)。

#### GET /api/business/users/{user_id}/status

内部接口，通过工具调用的状态查询。

### 个人数据管理 (Public APIs)

- `GET /api/business/me/plan`：读取当前有效学习计划
- `PUT /api/business/me/plan`：创建或更新当前学习计划
- `GET /api/business/me/profile`：读取有限长度用户画像文档
- `PUT /api/business/me/profile`：更新用户画像文档
- `GET /api/business/me/pause-requests`：查询暂停申请历史
- `POST /api/business/me/pause-requests`：写入一次暂停审批结果
- `GET /api/business/me/session-summaries`：查询历史会话总结
- `POST /api/business/me/session-summaries`：写入一条会话总结
- `GET /api/business/me/transactions`：查询当前用户相关流水

### 系统工具调用 (Internal APIs)

保留用于本地 System Agent 或者各类 Tools 的调用接口，这些接口支持显式指定 `user_id`：

- `GET /api/business/internal/users/{user_id}/plan`
- `PUT /api/business/internal/users/{user_id}/plan`
- `GET /api/business/internal/users/{user_id}/profile`
- `PUT /api/business/internal/users/{user_id}/profile`
- `GET /api/business/internal/users/{user_id}/pause-requests`
- `POST /api/business/internal/users/{user_id}/pause-requests`
- `GET /api/business/internal/users/{user_id}/session-summaries`
- `POST /api/business/internal/users/{user_id}/session-summaries`
- `GET /api/business/internal/users/{user_id}/transactions`

## 尚未实现或未闭环的功能

- Reward Pool 向用户返奖的正式接口逻辑
- 奖励任务的精细化创建、完成确认和发放
- Charity / Pool 的独立管理后台接口
