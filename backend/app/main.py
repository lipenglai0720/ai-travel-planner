"""创建 FastAPI 应用，并注册路由和异常处理函数。"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.routes.health import router as health_router
from app.api.routes.trips import router as trips_router
from app.core.config import Settings
from app.core.errors import request_validation_error_handler


settings = Settings()

app = FastAPI(
    title=settings.app_name,
    description="提供旅行规划相关的后端接口。",
    version="0.1.0",
)

# 将请求校验异常与我们的处理函数关联起来。
# 当请求输入校验失败时，FastAPI 调用这个函数生成响应。
app.add_exception_handler(
    RequestValidationError,
    request_validation_error_handler,
)

app.include_router(health_router)
app.include_router(
    trips_router,
    prefix="/api/v1",
)