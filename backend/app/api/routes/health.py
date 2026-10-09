"""系统健康检查路由：用于确认后端能够接收并响应 HTTP 请求。"""

from fastapi import APIRouter


# 创建路由对象，用来收集当前模块中的接口。
# tags 用于在 /docs 接口文档中分组，不会改变接口的 URL。
router = APIRouter(tags=["系统检查"])


# 将 health_check 函数注册为当前路由中的 GET /health 接口。
# 此处注册到 router，随后还需要在 main.py 中接入 FastAPI 应用。
@router.get(
    "/health",
    summary="检查后端服务是否运行",
)
def health_check() -> dict[str, str]:
    """返回服务状态和服务标识，确认当前后端能够正常响应。"""
    return {
        "status": "ok",
        "service": "ai-travel-planner",
    }