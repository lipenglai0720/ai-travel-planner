"""实况天气查询相关的 API 路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings
from app.models.common import ResponseMeta
from app.models.errors import ErrorResponse
from app.models.weather import WeatherLookupQuery
from app.models.weather_response import WeatherCurrentResponse
from app.services.weather_service import WeatherService


router = APIRouter(
    prefix="/weather",
    tags=["天气查询"],
)


def get_weather_service() -> WeatherService:
    """为本次请求创建天气服务，暂不发送高德请求。"""

    settings = Settings()

    return WeatherService(
        api_key=settings.amap_web_api_key,
        timeout_seconds=settings.amap_timeout_seconds,
    )


@router.get(
    "/current",
    response_model=WeatherCurrentResponse,
    status_code=200,
    summary="查询地区实况天气",
    description=(
        "先解析城市或区县，再查询高德实况天气。"
        "返回供应商发布时间、查询时间及数据限制提醒。"
    ),
    responses={
        404: {
            "model": ErrorResponse,
            "description": "没有找到符合规则的地区。",
        },
        422: {
            "model": ErrorResponse,
            "description": "输入不合法，或地区查询条件不明确。",
        },
        502: {
            "model": ErrorResponse,
            "description": "高德调用失败，或返回数据不合格。",
        },
        503: {
            "model": ErrorResponse,
            "description": "服务配置不正确，或天气暂不可用。",
        },
        504: {
            "model": ErrorResponse,
            "description": "高德请求超时。",
        },
    },
)
def get_current_weather(
    query: Annotated[
        WeatherLookupQuery,
        Query(),
    ],
    service: Annotated[
        WeatherService,
        Depends(get_weather_service),
    ],
) -> WeatherCurrentResponse:
    """调用天气服务，并包装统一成功响应。"""

    result = service.get_current_weather(query)

    warnings = [
        "本接口返回供应商实况天气，未来旅行日期需另行查询预报。",
        "供应商发布时间未提供时区，本次未计算天气数据年龄。",
    ]

    # 用面向用户的名称提示缺失字段。
    missing_fields: list[str] = []

    for attribute, label in [
        ("temperature_c", "温度"),
        ("humidity_percent", "湿度"),
        ("wind_direction", "风向"),
        ("wind_power", "风力"),
    ]:
        if getattr(result, attribute) is None:
            missing_fields.append(label)

    if missing_fields:
        warnings.append(
            "以下天气数据暂缺："
            + "、".join(missing_fields)
            + "。"
        )

    return WeatherCurrentResponse(
        data=result,
        meta=ResponseMeta(
            warnings=warnings,
        ),
    )