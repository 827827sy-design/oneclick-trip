# OneClick Trip AI Service

第一条真实联网工具链：城市解析与天气预报。

## 启动

```powershell
cd ai
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

接口文档：`http://127.0.0.1:8001/docs`

## 示例

```text
GET http://127.0.0.1:8001/tools/weather?city=成都&forecast_days=4
GET http://127.0.0.1:8001/tools/weather?city=当前位置&latitude=30.67&longitude=104.07
```

返回内容包含当前天气、未来预报、数据来源和抓取时间。城市名称通过 Open-Meteo Geocoding API 转换为经纬度，再调用 Forecast API。

## Dify/LangGraph

Dify Cloud 无法访问 `127.0.0.1`。本地验证完成后，需要部署 FastAPI 或通过临时 HTTPS 隧道暴露，然后将天气工具地址配置为：

```text
GET https://your-ai-service.example.com/tools/weather
```

正式版本建议把第三方地址全部放在 FastAPI Provider 内，不要让 Agent 直接抓取旅游网站页面。
