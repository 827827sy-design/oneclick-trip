# Agent Reach 联网研究 PoC（归档）

## 当前决策

2026-07-20 决定将 Agent Reach 从用户端 LangGraph 运行时移除。

它不再参与普通问答、行程规划、方案修改或预订，也不在前端显示“小红书搜索”或“全网研究”进度。原因是在线采集延长响应时间、结果噪声较高，并且难以稳定支撑实时旅游事实。

Agent Reach 代码与本次 PoC 结论保留，后续只作为 **B-02 管理端离线知识采集器**：管理员触发资料更新，经过 Pandas 清洗、来源分级、去重和质量检查后，再写入 Chroma 知识库。

## PoC 结论

- Agent Reach 版本：`1.5.0`。
- 上游：`mcporter 0.12.3 + Exa MCP`。
- 三组峨眉山检索均成功，每次返回 5 条去重后的结构化来源。
- 单次耗时约 3.0 至 3.8 秒，不包含后续正文读取和模型整理。
- 可补充攻略、游记、节奏和避坑经验。
- 不能作为天气、实时价格、票务余量、班次或安全规则的唯一事实来源。
- 数值事实需要官方来源或至少两个独立域名交叉验证。

## 离线架构

```text
管理员触发资料更新
  -> build_knowledge_research_registry
  -> Agent Reach / 小红书只读采集
  -> 来源分级与正文抓取
  -> Pandas 清洗、去重、字段标准化
  -> 管理员审核
  -> 文本切分与 Embedding
  -> Chroma 分知识库写入
```

## 安全边界

- 只允许固定诊断和只读采集命令。
- 用户输入不能成为可执行命令。
- 正文抓取拒绝本机地址和私网 IP。
- 小红书不使用个人主账号，不执行发布、评论、点赞等写操作。
- 原始采集数据不能直接成为行程中的实时事实。
- `build_live_tool_registry()` 永远不注册 Agent Reach 或小红书采集器。

## 保留入口

独立 PoC 仍可由开发者手动运行：

```powershell
.venv\Scripts\python.exe -m app.poc.agent_reach_cli --doctor
.venv\Scripts\python.exe -m app.poc.agent_reach_cli "峨眉山徒步登顶路线 完整时长" --limit 5
```

该入口不属于用户产品功能。
