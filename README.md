# 一键游 MVP

项目包含 Java 业务后端、MySQL、Vue 3 前端和 FastAPI AI 工具服务。FastAPI 天气接口已接入 Open-Meteo；当前 Dify/LangGraph 架构演示暂时使用完整 Mock 数据，不依赖公网服务。

如果第一次看不懂项目结构，先读：

```text
docs/project-structure.md
```

## 已完成的非 AI 闭环

- Spring Boot 3.x 后端工程
- MySQL 8.0 建表脚本和示例数据
- Spring Security + JWT 登录认证
- MyBatis-Plus 数据访问
- 城市、景点、美食、酒店、行程模板查询接口
- 规则版一键生成行程接口
- AI 助手 Java 占位接口
- FastAPI 真实天气与城市解析接口
- Vue 3 前端界面，沿用之前的小程序原型视觉
- 个人资料页：修改昵称、选择头像、退出登录

## 运行方式

### 1. 启动 MySQL

可以直接使用本机 MySQL，也可以在项目根目录运行：

```bash
docker compose up -d
```

默认账号密码：

```text
root / root
```

后端默认会连接 `localhost:3306/oneclick_trip`，用户名密码默认为 `root / root`。
如果使用自己的本机 MySQL，请设置环境变量：

```powershell
$env:MYSQL_URL="jdbc:mysql://localhost:3306/oneclick_trip?createDatabaseIfNotExist=true&useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai"
$env:MYSQL_USERNAME="root"
$env:MYSQL_PASSWORD="你的数据库密码"
$env:JWT_SECRET="本地开发用的一段较长随机字符串"
```

### 2. 启动 Spring Boot 后端

第一次运行时，先复制示例配置：

```bash
cp backend/src/main/resources/application-example.yml backend/src/main/resources/application.yml
```

然后把 `application.yml` 里的数据库密码改成自己的本机密码。`application.yml` 已加入 `.gitignore`，不要提交真实密码。

也可以不复制文件，直接使用环境变量覆盖配置。

在 `backend` 目录运行：

```bash
mvn spring-boot:run
```

默认服务地址：

```text
http://localhost:8080
```

示例账号：

```text
admin / 123456
user / 123456
```

### 3. 启动 Vue 3 前端

在 `frontend` 目录运行：

```bash
npm install
npm run dev
```

默认地址：

```text
http://127.0.0.1:5173
```

### 4. 启动 FastAPI AI 工具服务

在 `ai` 目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

接口文档：`http://127.0.0.1:8001/docs`

真实天气示例：`GET /tools/weather?city=成都&forecast_days=4`

## 核心接口

```text
POST /api/auth/login
POST /api/auth/register
GET  /api/cities
GET  /api/cities/{id}
GET  /api/cities/{id}/spots
GET  /api/cities/{id}/foods
GET  /api/cities/{id}/hotels
GET  /api/trip-templates
GET  /api/users/me
PUT  /api/users/me
POST /api/trip-plans/generate
GET  /api/trip-plans/{id}
POST /api/ai/chat
GET  http://127.0.0.1:8001/tools/weather
```

`POST /api/ai/chat` 现在会返回“AI 助手暂未接入”，用于给前端预留入口。

接口测试样例见：

```text
docs/api.http
```

## 协作开发建议

不要直接在 `main` 分支上开发。每个人从 `main` 拉新分支：

```bash
git checkout main
git pull
git checkout -b feature/your-feature-name
```

开发完成后提交并推送自己的分支：

```bash
git add .
git commit -m "feat: 描述本次功能"
git push -u origin feature/your-feature-name
```

然后在 GitHub 上创建 Pull Request，让另一位同学检查后再合并。
