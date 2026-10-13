"""将模型配置异常和旅行生成异常转换为 HTTP 响应。"""

from fastapi import Request
from fastapi.responses import JSONResponse
from app.clients.amap import AmapError
from app.llm.client import LLMConfigurationError
from app.models.errors import ApiError, ErrorResponse
from app.services.trip_generation_service import TripGenerationError
from app.services.weather_service import WeatherServiceError

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


def amap_error_handler(
    request: Request,
    exc: AmapError,
) -> JSONResponse:
    """将高德客户端异常转换为统一 HTTP 错误响应。"""

    if exc.code in (
        "amap_not_configured",
        "amap_configuration_invalid",
    ):
        status_code = 503
        message = "地点查询服务尚未正确配置，请检查服务端配置。"

    elif exc.code == "amap_timeout":
        status_code = 504
        message = "地点查询超时，请稍后重试。"

    else:
        status_code = 502
        message = "高德服务未能返回可用的地点数据，请稍后重试。"

    response = ErrorResponse(
        error=ApiError(
            # 保留客户端提供的稳定项目错误标识。
            code=exc.code,
            # HTTP 响应使用固定说明。
            # 不直接返回原始异常文本或高德请求 URL。
            message=message,
        )
    )

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )


# 这些映射是本项目天气接口的错误契约。
# 已有 POI 和旅行生成异常仍由各自处理器处理。
WEATHER_ERROR_RESPONSES: dict[str, tuple[int, str]] = {
    "district_not_found": (
        404,
        "没有找到符合规则的地区，请检查城市或区县名称。",
    ),
    "district_ambiguous": (
        422,
        "地区名称存在多个匹配，请补充省级编码或明确的 adcode。",
    ),
    "district_query_too_broad": (
        422,
        "地区查询范围过大，请提供更明确的名称或省级编码。",
    ),
    "district_level_unsupported": (
        422,
        "当前支持城市、区县和直辖市，请提供更具体的地区。",
    ),
    "weather_not_available": (
        503,
        "该地区实况天气本次暂不可用，请稍后重试。",
    ),
    "amap_not_configured": (
        503,
        "天气查询服务尚未正确配置，请检查服务端配置。",
    ),
    "amap_configuration_invalid": (
        503,
        "天气查询服务尚未正确配置，请检查服务端配置。",
    ),
    "amap_timeout": (
        504,
        "天气查询超时，请稍后重试。",
    ),
    "forecast_not_available": (
        503,
        "该地区短期天气预报本次暂不可用，请稍后重试。",
    ),
}


def weather_error_handler(
    request: Request,
    exc: WeatherServiceError,
) -> JSONResponse:
    """将天气服务异常转换为统一 HTTP 错误响应。"""

    status_code, message = WEATHER_ERROR_RESPONSES.get(
        exc.code,
        (
            502,
            "天气上游服务未能返回可用数据，请稍后重试。",
        ),
    )

    response = ErrorResponse(
        error=ApiError(
            code=exc.code,
            message=message,
        )
    )

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )