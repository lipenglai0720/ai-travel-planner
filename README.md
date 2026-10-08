# AI 智能旅行规划系统

这是一个使用 Python 和 FastAPI 逐步开发的智能旅行规划项目。

## 当前已完成

- 创建 FastAPI 后端应用。
- 提供 GET /health 健康检查接口。
- 提供自动生成的 API 文档。

## 开发环境

- Windows 11
- Python 3.11
- Miniconda，环境名称为 ai-travel
- PyCharm

## 安装依赖

先准备好 ai-travel Conda 环境，然后在项目根目录执行：

```powershell
conda run --no-capture-output -n ai-travel python -m pip install -r .\backend\requirements.txt
```

## 启动后端

在项目根目录执行：

```powershell
Set-Location .\backend

conda run --no-capture-output -n ai-travel python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## 验证接口

服务启动成功后，在另一个终端执行：

```powershell
curl.exe -i http://127.0.0.1:8000/health
```

预期 HTTP 状态码为 200，响应内容为：

```json
{"status":"ok","service":"ai-travel-planner"}
```

API 文档地址：http://127.0.0.1:8000/docs