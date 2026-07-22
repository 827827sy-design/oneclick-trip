# B-01 工具平台与真实数据适配

## 状态

**已完成（2026-07-20）**

B-01 的目标是让 LangGraph 通过统一契约调用外部旅游数据，并明确区分实时数据、缓存、AI 通用知识、Mock 与降级结果。

## 已完成内容

- 扩展统一 `ToolResult`：`source`、`data_mode`、`confidence`、`fetched_at`、`bookable`。
- 建立 `ToolRegistry`、代码白名单、统一执行器、错误恢复与最多一次重试。
- 接入 Open-Meteo，提供真实天气、当前气温和逐日预报。
- 接入 Nominatim，解析行政区和候选景点的可信经纬度。
- 接入 OSRM，仅使用 Provider 验证过的坐标计算真实路段距离与时间。
- 坐标缺失或服务失败时拒绝生成虚假路线距离。
- 定义酒店、火车、飞机、门票 Provider 契约，后续取得合规供应商凭证后可替换实现。
- 正式应用与测试 Mock 分离；正式 `create_app()` 只装配真实用户工具。
- Agent Reach 与小红书采集器从用户运行时移除，只保留给 B-02 管理端离线知识采集。

## 用户运行时边界

```text
weather_query
  -> Open-Meteo

trip_plan phase 1
  -> Open-Meteo
  -> DeepSeek 生成候选
  -> Nominatim 验证候选景点坐标

trip_plan phase 2
  -> OSRM 计算候选路线
  -> DeepSeek 整理开放时间、门票参考和完整行程
```

用户请求不会执行 `travel_research` 或 `xiaohongshu_research`。这些采集器位于独立的 `build_knowledge_research_registry()`，供 B-02 后台知识库更新流程使用。

## 供应商接口边界

酒店库存、火车班次、航班、门票余量和真实价格需要供应商授权。本阶段只完成稳定接口契约，不伪造实时数据：

- `HotelProvider`
- `TrainProvider`
- `FlightProvider`
- `TicketProvider`

预订安全、确认令牌、幂等、支付与第三方下单仍由 Java 后端负责。

## 真实验收

2026-07-20 使用“成都三日游”完成真实冒烟：

- Open-Meteo 天气成功，`data_mode=REALTIME`。
- Nominatim 成功验证 5/5 个景点坐标。
- OSRM 成功返回 4 个路段，总距离约 43.9 km，总驾驶时间约 60 分钟。
- 本轮工具错误为 0。
- 本轮仅调用 `weather`、`poi_coordinates`、`route_matrix`，没有 Agent Reach 或小红书工具。

自动化验证：AI 测试 254 项通过，Vue 生产构建通过。

## 英文术语

| 术语 | 中文解释 |
|---|---|
| Tool | Agent 可以调用的一项外部能力 |
| Provider | 实际提供数据的服务商或数据源 |
| Adapter | 把供应商格式转换为项目统一格式的适配器 |
| Registry | 记录系统允许调用哪些工具的注册表 |
| ToolResult | 所有工具统一使用的返回信封 |
| REALTIME | 本次从外部服务实时获取的数据 |
| CACHE | 从仍在有效期内的缓存读取的数据 |
| AI_KNOWLEDGE | 大模型基于通用知识生成的建议，不是实时查询 |
| MOCK | 为自动化测试准备的模拟数据 |
| FALLBACK | 外部工具失败后的降级结果 |
| Timeout | 请求超过限定时间仍未返回 |
| Retry | 工具失败后按规则再次尝试 |

## 下一阶段

B-02 使用 Pandas 建立后台资料清洗、去重、字段标准化和质量报告，再写入 Chroma。Agent Reach 可作为该离线流程的原始资料来源之一，但不进入用户实时会话。
