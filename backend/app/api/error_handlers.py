"""将模型配置异常和旅行生成异常转换为 HTTP 响应。"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.llm.client import LLMConfigurationError
from app.models.errors import ApiError, ErrorResponse
from app.services.trip_generation_service import TripGenerationError


# 接口对外提供固定的错误说明。
# 不直接把异常文本、模型原始输出或上游响应放进 HTTP 响应。
GENERATION_ERROR_MESSAGES: dict[str, str] = {
    "llm_timeout": "生成旅行草案超时，请稍后重试。",
    "llm_connection_error": "暂时无法连接模型服务，请稍后重试。",
    "llm_http_error": (
        "模型服务未能完成请求，请检查服务配置或稍后重试。"
    ),
}


def llm_configuration_error_handler(
    request: Request,
    exc: LLMConfigurationError,
) -> JSONResponse:
    """模型 Key 尚未正确配置时，返回统一的 503 响应。"""

    # request 和 exc 是 FastAPI 异常处理器约定的参数。
    # 当前处理器只使用固定的对外说明。
    response = ErrorResponse(
        error=ApiError(
            code="llm_not_configured",
            message="旅行生成服务尚未配置，请检查服务端模型配置。",
        )
    )

    # ErrorResponse 会通过默认工厂创建 ResponseMeta。
    # mode="json" 将其中的 UUID 转换为 JSON 兼容的字符串。
    return JSONResponse(
        status_code=503,
        content=response.model_dump(mode="json"),
    )


def trip_generation_error_handler(
    request: Request,
    exc: TripGenerationError,
) -> JSONResponse:
    """将已经识别的旅行生成失败转换为统一错误响应。"""

    # 模型超时使用 504。
    # 其他已识别的上游调用失败或生成结果失败使用 502。
    status_code = 504 if exc.code == "llm_timeout" else 502

    message = GENERATION_ERROR_MESSAGES.get(
        exc.code,
        "本次旅行草案生成失败，请稍后重试。",
    )

    response = ErrorResponse(
        error=ApiError(
            # 保留服务层提供的稳定错误标识。
            # 前端可以根据 code 区分超时、输出不合格等情况。
            code=exc.code,
            message=message,
        )
    )

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )