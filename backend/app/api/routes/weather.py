"""实况天气查询相关的 API 路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings
from app.models.common import ResponseMeta
from app.models.errors import ErrorResponse
from app.models.weather import WeatherLookupQuery
from app.models.weather_response import (
    WeatherCurrentResponse,
    WeatherForecastResponse,
    WeatherForecastRangeResponse,
)
from app.services.weather_service import WeatherService
from app.models.forecast_lookup import ForecastLookupQuery
from app.models.forecast_range import ForecastRangeQuery
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

@router.get(
    "/forecast",
    response_model=WeatherForecastResponse,
    status_code=200,
    summary="查询短期天气预报",
    description=(
        "查询实际可用的逐日预报，可选检查一个目标日期。"
        "合法日期没有记录时返回 200，并标记 unavailable。"
    ),
    responses={
        404: {
            "model": ErrorResponse,
            "description": "没有找到符合规则的地区。",
        },
        422: {
            "model": ErrorResponse,
            "description": "输入不合法，或地区条件不明确。",
        },
        502: {
            "model": ErrorResponse,
            "description": "高德调用失败，或预报数据不合格。",
        },
        503: {
            "model": ErrorResponse,
            "description": "服务配置不正确，或预报暂不可用。",
        },
        504: {
            "model": ErrorResponse,
            "description": "高德请求超时。",
        },
    },
)
def get_forecast(
    query: Annotated[
        ForecastLookupQuery,
        Query(),
    ],
    service: Annotated[
        WeatherService,
        Depends(get_weather_service),
    ],
) -> WeatherForecastResponse:
    """调用预报服务，并包装统一成功响应。"""

    result = service.get_forecast(query)

    warnings = [
        "这些数据属于供应商天气预报，实际天气可能变化。",
        "供应商发布时间未提供时区，本次未计算预报数据年龄。",
    ]

    if (
        result.coverage_status == "unavailable"
        and result.target_date is not None
    ):
        warnings.append(
            "当前返回的短期预报中没有 "
            f"{result.target_date.isoformat()} 的记录。"
        )

    # 对完整预报中的缺失字段提供日期明确的提醒。
    for day in result.forecast.days:
        missing_fields: list[str] = []

        for attribute, label in [
            ("day_temperature_c", "白天温度"),
            ("night_temperature_c", "夜间温度"),
            ("day_wind_direction", "白天风向"),
            ("night_wind_direction", "夜间风向"),
            ("day_wind_power", "白天风力"),
            ("night_wind_power", "夜间风力"),
        ]:
            if getattr(day, attribute) is None:
                missing_fields.append(label)

        if missing_fields:
            warnings.append(
                f"{day.forecast_date.isoformat()} "
                "的以下预报字段暂缺："
                + "、".join(missing_fields)
                + "。"
            )

    return WeatherForecastResponse(
        data=result,
        meta=ResponseMeta(
            warnings=warnings,
        ),
    )


@router.get(
    "/forecast-range",
    response_model=WeatherForecastRangeResponse,
    status_code=200,
    summary="查询旅行期间天气与出行建议",
    description=(
        "根据旅行起止日期检查实际预报覆盖情况，"
        "返回每日天气记录与项目规则建议。"
        "缺少部分或全部旅行日期的预报时，"
        "仍返回 200，并明确标记缺失日期。"
    ),
    responses={
        404: {
            "model": ErrorResponse,
            "description": "没有找到符合规则的地区。",
        },
        422: {
            "model": ErrorResponse,
            "description": "参数不合法，或地区条件不明确。",
        },
        502: {
            "model": ErrorResponse,
            "description": "高德调用失败，或预报数据不合格。",
        },
        503: {
            "model": ErrorResponse,
            "description": "服务配置不正确，或预报暂不可用。",
        },
        504: {
            "model": ErrorResponse,
            "description": "高德请求超时。",
        },
    },
)
def get_forecast_range(
    query: Annotated[
        ForecastRangeQuery,
        Query(),
    ],
    service: Annotated[
        WeatherService,
        Depends(get_weather_service),
    ],
) -> WeatherForecastRangeResponse:
    """查询区间天气，并包装统一成功响应。"""

    result = service.get_forecast_range(query)

    warnings = [
        "这些数据属于供应商天气预报，实际天气可能变化。",
        "供应商发布时间未提供时区，本次未计算预报数据年龄。",
        "出行建议依据预报和项目规则生成，出发前请核对最新信息。",
    ]

    if result.coverage.missing_dates:
        missing_dates_text = "、".join(
            day.isoformat()
            for day in result.coverage.missing_dates
        )

        warnings.append(
            f"以下旅行日期暂无预报：{missing_dates_text}。"
            "对应天气信息保留为空。"
        )

    for item in result.daily_weather:
        if item.missing_fields:
            warnings.append(
                f"{item.travel_date.isoformat()} "
                "的以下预报字段暂缺："
                + "、".join(item.missing_fields)
                + "。"
            )

    return WeatherForecastRangeResponse(
        data=result,
        meta=ResponseMeta(
            warnings=warnings,
        ),
    )