# Dify 导入说明

推荐导入 v4 安全主骨架：

`oneclick-trip-multi-agent-v4.yml`

它在 v3 基础上增加校验写入闸门、旧草稿失效、确认令牌、预订槽位守卫、工具白名单和恢复状态回写。

需要查看上一版时，可以导入 v3：

`oneclick-trip-multi-agent-v3.yml`

它在 v2 基础上增加跨轮检查点、预订草稿绑定、工具失败恢复和 Flash/Pro 模型分层。

如需保留原演示流程，也可以导入 v2：

`01-导入Dify-oneclick-trip-multi-agent.yml`

不要上传 `build_v2_dsl.py`、`build_v3_dsl.py` 或 `build_v4_dsl.py`。它们是开发阶段用于重新生成 YAML 的 Python 脚本，Dify 无法直接导入 Python 文件。

如果需要重新生成 DSL，可在项目目录运行：

```powershell
python ai\dify\build_v2_dsl.py
python ai\dify\build_v3_dsl.py
python ai\dify\validate_v3_dsl.py
python ai\dify\build_v4_dsl.py
python ai\dify\validate_v4_dsl.py
```

运行后导入生成的 `.yml` 文件，不是导入脚本本身。

当前 DSL 是纯 Mock 演示模式，不依赖公网 FastAPI。所有天气、酒店、交通、景点、门票和预订数据都明确标记为 `MOCK`。

为兼容 Dify 的对象深度上限，深层 Mock 数据通过 JSON 字符串传递。这不会影响 LangGraph 后续使用结构化 State。
