"""后端应用入口：创建 FastAPI 应用，并接入各功能模块的路由。"""

from fastapi import FastAPI

from app.api.routes.health import router as health_router


# 创建整个后端应用。
# title、description、version 会展示在自动生成的接口文档中。
app = FastAPI(
    title="AI 智能旅行规划系统",
    description="提供旅行规划相关的后端接口。",
    version="0.1.0",
)

# 将健康检查模块中的路由接入应用。
# 接入后，应用才能通过 GET /health 调用对应的处理函数。
app.include_router(health_router)