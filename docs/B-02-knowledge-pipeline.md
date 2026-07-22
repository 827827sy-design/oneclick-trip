# B-02 Pandas 知识清洗与发布管道

## 状态

**已完成（2026-07-21）**

B-02 将 B-01 保留的离线采集能力接入管理后台。它不是用户实时会话的一部分，而是一条由管理员控制的知识生产流程。

## 业务流程

```text
管理员手工录入 / Agent Reach 离线采集
  -> RawKnowledgeRecord 原始资料
  -> Pandas 批量标准化
  -> 字段完整性检查
  -> 城市标签与标题/正文一致性审计
  -> 规范化 URL 与内容指纹去重
  -> 来源分级与质量评分
  -> 生成待审核批次和质量报告
  -> 管理员查看通过项与拒绝原因
  -> 人工确认发布
  -> 文本切分
  -> 按 poi / food / hotel / transport / ticket / guide 写入 Chroma
  -> 已通过资料发现问题时，填写原因并从批次和 Chroma 精确删除
  -> 索引异常时，以已发布审核记录为事实源一键重建 Chroma
  -> 用户 Agent 使用向量 + BM25 混合检索与质量重排序
```

未经人工确认的批次不会写入向量数据库。被拒绝或重复的资料只保留在质量报告中，不参与用户端 RAG 检索。

## Pandas 清洗内容

- 使用 `DataFrame` 批量处理原始资料，而不是逐条手写字符串逻辑。
- 清除多余空白和不可见字符。
- 将“成都市”标准化为“成都”。
- 将“景区、餐饮、住宿”等别名映射为统一类别和知识库。
- 规范化来源链接，去除 `utm_*`、`spm` 等跟踪参数。
- 规范化标签并移除重复标签。
- 检查标题、正文、城市、类别和知识库是否有效。
- 对常见国内目的地进行城市一致性审计：明显讲述其他目的地的资料以 `CITY_CONTENT_MISMATCH` 拒绝，正文未出现城市且无冲突的资料保留但降低质量分，合理的跨城对比不误拒。
- 优先按规范化 URL 去重，无 URL 时按文本指纹去重。
- 根据正文长度、来源链接、来源等级和标签计算 `0~1` 质量分。
- 输出输入数、通过数、拒绝数、重复数、完整率、官方来源率和平均质量分。
- Agent Reach 搜索摘要最多保留 1200 字，但后台会继续抓取每个候选来源最多 50000 字的网页正文；只有抓取失败的来源才使用摘要降级。
- 完整正文单页最多保留 50,000 字，随后切分入库，不会把全文作为一个超长向量块。

## 持久化与隔离

- Chroma 按知识类型使用独立 collection。
- 文档元数据包含批次、记录、分块、城市、城市一致性、识别出的目的地、来源、来源等级、URL、质量分和标签。
- 文档同时记录正文来自完整网页、搜索摘要降级或管理员录入；摘要降级项会降低质量分。
- 审核批次保存在 `.data/knowledge_batches.json`，FastAPI 重启后仍能继续审核。
- 批次仓库通过 `KnowledgeBatchRepository` 抽象，后续可以替换为 MySQL 实现。
- `build_live_tool_registry()` 只包含用户端允许使用的实时工具。
- `build_knowledge_research_registry()` 单独装配 Agent Reach，只供管理端离线采集。

## 管理端入口

管理员登录后打开：

```text
http://127.0.0.1:5174/#/knowledge
```

页面支持：

- 查看向量文档、清洗批次、待审核和已发布数量。
- 手工录入多条资料。
- 一键填入包含重复项和缺失项的答辩演示数据。
- 运行 Pandas 清洗并查看质量报告。
- 分别查看通过资料与拒绝原因。
- 人工确认后发布到 Chroma。
- 删除已通过资料；若资料已经发布，会同步删除 Chroma 中对应的全部分块。
- 查看删除审计，包括资料标题、操作人、原因、时间和移除分块数。
- 在启用 `AGENT_REACH_ENABLED=true` 时由管理员执行离线采集。
- 查看历史批次并在服务重启后继续审核。
- 一键重建向量索引，清除孤立分块和旧元数据，仅恢复已发布且人工通过的资料。

## 接口边界

对前端公开的接口由 Spring Security 保护，仅管理员可调用：

```text
GET  /api/admin/knowledge/stats
POST /api/admin/knowledge/rebuild
GET  /api/admin/knowledge/batches
GET  /api/admin/knowledge/batches/{batchId}
POST /api/admin/knowledge/preview
POST /api/admin/knowledge/collect
POST /api/admin/knowledge/batches/{batchId}/publish
DELETE /api/admin/knowledge/batches/{batchId}/records/{recordId}
```

Java 再代理到 FastAPI 的 `/v1/internal/knowledge/*`。生产部署时应保证 FastAPI 内部端口不直接暴露公网。

## 用户侧混合检索

已审核发布的资料通过 `knowledge_search` 进入普通旅游问答和完整行程第一阶段：

```text
用户问题
  -> BGE-small-zh-v1.5 生成 512 维中文语义向量
  -> Chroma 向量候选召回
  +  BM25 中文关键词候选召回
  -> 合并候选
  -> 语义分 + 关键词分 + 资料质量 + 来源等级 + 精确短语重排序
  -> 将命中文本与来源链接交给回答或规划 Agent
```

Agent Reach 仍然只在后台离线采集时运行。用户问答只读取已经审核的 Chroma 知识，不会临时联网抓取网页。

## BGE 模型

运行时使用 `bge-small-zh-v1.5` 的 ONNX INT8 版本，在 CPU 上生成 512 维归一化向量。模型文件不提交 Git，首次部署需要下载到 `.data/models/bge-small-zh-v1.5`：

```powershell
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Xenova/bge-small-zh-v1.5', local_dir='.data/models/bge-small-zh-v1.5', allow_patterns=['tokenizer.json','tokenizer_config.json','special_tokens_map.json','vocab.txt','config.json','onnx/model_quantized.onnx'])"
```

`CHROMA_COLLECTION` 使用 `travel_knowledge_bge_v15`，与旧 Hash 384 维集合隔离。模型或维度变化时必须使用新集合或重新向量化，禁止混用旧向量。

## 关键文件

```text
ai/travel_agent/app/knowledge_pipeline/cleaner.py
ai/travel_agent/app/knowledge_pipeline/chunker.py
ai/travel_agent/app/knowledge_pipeline/repository.py
ai/travel_agent/app/knowledge_pipeline/service.py
backend/src/main/java/com/oneclicktrip/controller/admin/AdminKnowledgeController.java
frontend-admin/src/views/KnowledgePipeline.vue
```

## 英文术语

| 术语 | 中文解释 |
|---|---|
| Pipeline | 将采集、清洗、审核和发布连接起来的处理管道 |
| DataFrame | Pandas 的二维表格数据结构，可批量处理多行数据 |
| Normalize | 将不同写法整理成统一格式，即标准化 |
| Deduplicate | 找出并移除重复资料，即去重 |
| Fingerprint | 根据文本计算的稳定摘要，用来识别内容重复 |
| Quality Score | 对资料完整性和可信度计算的质量分 |
| Source Tier | 官方、可信编辑、商业平台、社区等来源等级 |
| Chunk | 为向量检索切分出的较短文本块 |
| Embedding | 把文本转换为可计算语义相似度的向量 |
| Collection | Chroma 中隔离某类知识的一组向量文档 |
| Preview | 发布前的清洗结果预览和人工审核状态 |
| Publish | 将审核通过的数据正式写入向量知识库 |

## 验证

人工审核状态机采用以下规则：

```text
PENDING（待审核）
  -> APPROVED（人工通过）
  -> REJECTED（人工拒绝，必须填写原因）
  -> PENDING（恢复审核）

APPROVED（已通过）
  -> DELETED（删除，必须填写原因；已发布时同步移除 Chroma 分块）

批次 PREVIEWED
  -> PUBLISHED（仅写入非拒绝资料）
  -> REJECTED（整批驳回，禁止发布）
  -> PREVIEWED（恢复审核）
```

审核人由 Spring Security 中的 JWT 登录信息注入，前端不能自行指定。每条人工决策保存审核状态、审核人、审核时间、拒绝原因和备注。删除操作额外保存独立审计记录，删除前的资料不会继续出现在有效记录列表中。

问答 Agent 与规划 Agent 均把检索正文视为不可信数据，只允许提取旅游事实，不执行正文中夹带的命令、角色设定或提示词，从消费端降低网页提示注入风险。

新增管理接口：

```text
POST /api/admin/knowledge/batches/{batchId}/records/{recordId}/review
DELETE /api/admin/knowledge/batches/{batchId}/records/{recordId}
POST /api/admin/knowledge/batches/{batchId}/reject
POST /api/admin/knowledge/batches/{batchId}/reopen
```

## 后续增强项

- 已发布整批撤回并从 Chroma 删除对应向量。
- 将本地 JSON 审核仓库替换为 MySQL，实现多人并发和数据库审计日志。
- 支持管理员直接修改清洗后的正文与元数据，再重新计算质量分。
- 增加资料有效期、过期提醒和定时重新采集。
- 为 FastAPI 内部管理接口增加服务间签名或内网网关保护。
- 建立 RAG 评测集，量化 Recall@K、排序准确率和引用正确率。
- 如数据量显著增长，再接入独立 Cross-Encoder reranker；当前使用 BGE、BM25Plus 与质量分加权重排。

- Pandas 清洗、去重、质量报告、批次持久化、Chroma 发布和内部接口均有自动化测试。
- Spring Boot 管理接口通过 Maven 测试。
- Vue 管理后台通过 Vite 生产构建。
