# B-05 集成环境与自动化测试

## 环境组成

| 组件 | 默认地址 | 用途 |
| --- | --- | --- |
| MySQL 8 | `127.0.0.1:3306` | Java 业务数据、偏好、方案版本、订单草稿、运行日志 |
| Redis 7.4 | `127.0.0.1:6379` | LangGraph checkpoint、临时确认状态 |
| Chroma 1.5.9 | `http://127.0.0.1:8001` | 旅游知识库向量检索 |
| FastAPI | `http://127.0.0.1:8000` | LangGraph Agent 服务 |
| Spring Boot | `http://127.0.0.1:8080` | 认证、业务、安全边界和管理接口 |
| 用户端 | `http://127.0.0.1:5173` | Vue 3 用户界面 |
| 管理端 | `http://127.0.0.1:5174` | Vue 3 管理后台 |

## 新环境启动

1. 准备环境变量。根目录 `.env.example` 是完整清单，FastAPI 使用 `ai/travel_agent/.env.example`。
2. 不要把真实数据库密码、DeepSeek Key、JWT Secret 或内部服务密钥提交到 Git。
3. 启动基础设施：

```powershell
docker compose up -d mysql redis chroma
```

4. FastAPI 使用容器 Chroma 时设置：

```powershell
$env:CHROMA_SERVER_URL='http://127.0.0.1:8001'
```

未设置 `CHROMA_SERVER_URL` 时，系统继续使用 `CHROMA_PERSIST_DIRECTORY` 指定的本地持久化 Chroma，便于无 Docker 的课堂演示。

5. 双击 `tools/start-oneclick-trip.cmd`，或执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools/start-oneclick-trip.ps1
```

6. 验证所有组件：

```powershell
powershell -ExecutionPolicy Bypass -File tools/verify-oneclick-trip.ps1 -RequireChroma
```

使用本机 MySQL/Redis 且不启动 Chroma Server 时，去掉 `-RequireChroma`。Chroma 检查会显示但不作为失败条件。

## 自动化测试

### Python Agent

```powershell
cd ai/travel_agent
.venv/Scripts/python -m pytest -q
```

### Java 与跨服务合同

```powershell
cd backend
mvn test -s maven-settings.xml
```

`FastApiAgentClientIntegrationTest` 会启动本地 HTTP Stub，实际序列化 Spring 请求并验证 FastAPI 的 `conversation_id`、`user_id`、`message` 及响应字段契约。测试不需要调用大模型，也不会消耗 API 额度。

### Vue 构建

```powershell
cd frontend
npm run build
cd ../frontend-admin
npm run build
```

## 替换真实环境

- MySQL：修改 `MYSQL_URL`、`MYSQL_USERNAME`、`MYSQL_PASSWORD`
- Redis：修改 `REDIS_URL`
- Chroma Server：修改 `CHROMA_SERVER_URL`
- FastAPI 地址：修改 `AI_SERVICE_BASE_URL`
- Java 内部接口：FastAPI 与 Spring 必须配置相同的 `AI_INTERNAL_SERVICE_SECRET`
- DeepSeek：只通过部署环境注入 `DEEPSEEK_API_KEY`

部署时应为 MySQL、Redis、Chroma 配置网络访问控制与认证，不直接暴露到公网。
