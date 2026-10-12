"""创建 FastAPI 应用，并注册路由和异常处理函数。"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.error_handlers import (
    llm_configuration_error_handler,
    trip_generation_error_handler,
)
from app.api.routes.health import router as health_router
from app.api.routes.trips import router as trips_router
from app.core.config import Settings
from app.core.errors import request_validation_error_handler
from app.llm.client import LLMConfigurationError
from app.services.trip_generation_service import TripGenerationError


settings = Settings()

app = FastAPI(
    title=settings.app_name,
    description="提供旅行规划相关的后端接口。",
    version="0.1.0",
)

# 请求输入校验失败时，返回已有的统一 422 响应。
app.add_exception_handler(
    RequestValidationError,
    request_validation_error_handler,
)

# 模型 Key 尚未配置时，返回统一的 503 响应。
# 该异常可能发生在生成服务依赖的初始化过程中。
app.add_exception_handler(
    LLMConfigurationError,
    llm_configuration_error_handler,
)

# 已识别的生成异常，统一转换为 502 或 504 响应。
app.add_exception_handler(
    TripGenerationError,
    trip_generation_error_handler,
)

app.include_router(health_router)
app.include_router(
    trips_router,
    prefix="/api/v1",
)