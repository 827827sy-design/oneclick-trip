# 一键游 v4 测试用例

## 自动验证

```powershell
cd "C:\Users\20343\Documents\New project\oneclick-trip\ai\dify"
python build_v4_dsl.py
python validate_v4_dsl.py
```

通过标准：输出 `PASS: all v4 safety gates and negative-path tests`。

## Dify 手工测试

| ID | 操作 | 预期结果 |
| --- | --- | --- |
| V4-01 | 让 Planner 返回非 JSON | 第一次硬校验失败；即使软评审误判 pass，也只能进入修订 |
| V4-02 | 让 Revision 返回非 JSON 或缺少 `plan_id` | 第二轮校验失败，不保存方案 |
| V4-03 | 修改方案时让模型返回坏 JSON | 显示修改失败，Conversation Variable 中旧方案不变 |
| V4-04 | 生成方案 V1 和订单草稿，再生成方案 V2 | 保存 V2 时 `booking_draft_json` 被清空，V1 草稿不可确认 |
| V4-05 | `帮我预订酒店`，不指定 option_id | 不生成草稿，列出当前方案可预订选项并追问 |
| V4-06 | 使用不属于当前方案的 option_id | 返回 `OPTION_NOT_IN_CURRENT_PLAN` |
| V4-07 | 用酒店 option_id 请求预订火车 | 返回 `OPTION_TYPE_MISMATCH` |
| V4-08 | 选择有效 option_id | 生成唯一 `draft_id`、`confirmation_token`、`draft_hash` 和 `idempotency_key` |
| V4-09 | 只回复 `确认预订` | 拒绝提交，要求 draft_id/令牌 |
| V4-10 | 使用正确 draft_id 和令牌确认 | Mock 提交成功，草稿状态变为 `SUBMITTED` |
| V4-11 | 篡改草稿价格或 quote_ids | 返回 `DRAFT_HASH_MISMATCH` |
| V4-12 | 用 V1 草稿确认 V2 方案 | 返回 `DRAFT_PLAN_VERSION_MISMATCH` |
| V4-13 | LLM 请求 `weather + hotel_search + evil_admin_tool` 处理天气 | 只执行 `weather`，其余进入 `ignored_tools` |
| V4-14 | 只提供开始日期，没有天数和结束日期 | 进入偏好补全，不执行完整规划 |
| V4-15 | 首次请求 `把第二天换成熊猫基地` | 返回当前没有可修改方案，不生成默认成都方案 |
| V4-16 | 阶段 1 模拟天气失败后重试成功 | Planner State 中天气状态为 `MOCK_RETRY_SUCCESS` |
