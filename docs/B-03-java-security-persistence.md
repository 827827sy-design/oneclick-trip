# B-03 Java 安全与业务持久化

## 目标

B-03 将用户身份、长期业务数据和预订安全边界收回 Spring Boot。LangGraph 负责编排和生成，不能把 State、请求体 `userId` 或模型输出当作业务授权依据。

## 身份边界

- `/api/ai/chat`、`/api/ai/chat/async`、`/api/ai/jobs/**` 和 `/api/ai/resume` 必须携带 JWT。
- Java 只使用 `JwtUser.userId`，旧请求体中的 `userId` 字段不会参与身份判断。
- 会话 ID 和异步 runId 都校验所有者，不能跨用户查看或恢复。
- FastAPI 调 Java 使用独立的 `X-Internal-Service-Key`，仅开放 `/api/internal/**`。
- 内部共享密钥通过 `AI_INTERNAL_SERVICE_SECRET` 注入，不写入代码仓库。

## 数据所有权

Flyway 迁移 `V20260722_01__b03_agent_persistence.sql` 创建：

```text
ai_user_travel_preferences  长期旅行偏好与版本
ai_travel_plan_versions     不可变方案版本与当前版本指针
ai_booking_draft            订单草稿、安全确认与幂等状态
```

原有 `ai_conversation`、`ai_message` 继续由 Java 保存会话和消息。FastAPI 在外部基础设施模式下通过 Java 内部接口读写偏好和方案，不再直接把它们作为自己的安全边界。

## 内部接口

```text
GET  /api/internal/ai/users/{userId}/preferences
PUT  /api/internal/ai/users/{userId}/preferences

GET  /api/internal/ai/plans/current?user_id=...&conversation_id=...
POST /api/internal/ai/plans/versions

POST /api/internal/ai/booking-drafts
GET  /api/internal/ai/booking-drafts/{draftId}?user_id=...
POST /api/internal/ai/booking-drafts/{draftId}/confirm
POST /api/internal/ai/booking-drafts/{draftId}/cancel
```

## 方案版本规则

- 新方案的首个版本必须为 `1`。
- 同一 `plan_id` 的后续版本只能在当前版本上递增 `1`。
- 相同版本和相同内容重复保存按幂等成功处理。
- 相同版本写入不同内容会被拒绝。
- 保存新版本时，旧版本保留但 `is_current` 变为 `0`。

## 预订安全规则

1. 创建草稿前必须确认用户、会话、`plan_id` 和 `plan_version` 对应当前方案。
2. `selected_option_ids` 必须来自当前方案，不能让模型构造任意商品 ID。
3. confirmation token 使用安全随机数生成，MySQL 只保存 SHA-256 hash。
4. 原始 token 不写入 `TravelState`；FastAPI 临时保存在 Redis，内存仅作为降级。
5. 确认时再次校验用户、会话、方案版本、token、过期时间和草稿状态。
6. 相同幂等键重复确认返回原结果，不同幂等键不能重复处理同一草稿。
7. 当前仍是预订架构演示，不执行支付或第三方供应商下单。

## 环境变量

```text
BUSINESS_BACKEND=java
JAVA_BACKEND_BASE_URL=http://127.0.0.1:8080
AI_INTERNAL_SERVICE_SECRET=<Java 与 FastAPI 共用的随机密钥>
```

## 自动化验证

- Java：JWT 服务边界、异步任务所有权、内部服务密钥、确认幂等。
- Python：Java 偏好仓库、方案仓库、预订草稿协议及 token 不进入 State。
- 运行测试必须使用项目要求的 JDK 17。
