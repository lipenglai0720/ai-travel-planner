"""后端应用入口：创建 FastAPI 应用并注册健康检查接口。"""

from fastapi import FastAPI


# FastAPI 是一个类；调用 FastAPI(...) 会创建应用对象。
# title、description、version 会展示在自动生成的接口文档中。
app = FastAPI(
    title="AI 智能旅行规划系统",
    description="提供旅行规划相关的后端接口。",
    version="0.1.0",
)


# 将下面的函数注册为 GET /health 请求的处理函数。
# summary 和 tags 用于说明接口、组织接口文档。
@app.get(
    "/health",
    summary="检查后端服务是否运行",
    tags=["系统检查"],
)
def health_check() -> dict[str, str]:
    """返回当前服务标识，用于确认后端能够正常响应请求。"""
    return {
        "status": "ok",
        "service": "ai-travel-planner",
    }