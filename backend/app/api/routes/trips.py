"""旅行规划相关的 API 路由。"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings
from app.llm.client import create_trip_chat_model
from app.models.common import (
    ErrorResponse,
    ResponseMeta,
)
from app.models.trip import (
    TripGenerationResponse,
    TripPlanRequest,
    TripPlanResponse,
    TripPreviewResponse,
    TripRequest,
)
from app.services.trip_generation_service import TripGenerationService
from app.services.trip_planning_service import TripPlanningService
from app.services.trip_service import TripService
from app.services.weather_service import WeatherService


router = APIRouter(
    prefix="/trips",
    tags=["旅行规划"],
)


def get_trip_service() -> TripService:
    """创建本次接口调用使用的旅行服务。"""
    return TripService()


def get_trip_generation_service() -> Iterator[TripGenerationService]:
    """为本次请求提供生成服务，并在使用结束后关闭同步客户端。"""

    settings = Settings()

    # 创建客户端只完成初始化。
    # 真正的云端请求由 generate_draft() 内部的 invoke() 发起。
    chat_model = create_trip_chat_model(settings)

    try:
        # yield 将服务交给 FastAPI，然后暂停本函数。
        yield TripGenerationService(chat_model)
    finally:
        # 当前服务使用同步 invoke()。
        # 路由执行结束后，关闭本次请求使用的同步 HTTP 客户端。
        # 生成过程中抛出异常时，这段清理代码也会执行。
        chat_model.root_client.close()


def get_trip_planning_service(
    generation_service: Annotated[
        TripGenerationService,
        Depends(
            get_trip_generation_service,
            scope="function",
        ),
    ],
) -> TripPlanningService:
    """复用生成服务的生命周期，再组合天气服务。"""

    settings = Settings()

    # WeatherService 这里只保存配置。
    # 是否真正查询天气，由 create_plan() 的 include_weather 决定。
    return TripPlanningService(
        generation_service=generation_service,
        weather_service=WeatherService(
            api_key=settings.amap_web_api_key,
            timeout_seconds=settings.amap_timeout_seconds,
        ),
    )


@router.post(
    "/preview",
    response_model=TripPreviewResponse,
    status_code=200,
    summary="预览旅行需求",
    description="校验旅行输入，返回日期、人数、房间数和预算摘要。",
    responses={
        422: {
            "model": ErrorResponse,
            "description": "请求参数校验失败，返回统一错误结构。",
        }
    },
)
def preview_trip(
    trip_request: TripRequest,
    service: Annotated[
        TripService,
        Depends(get_trip_service),
    ],
) -> TripPreviewResponse:
    """调用旅行服务生成经过校验的需求摘要。"""

    preview = service.preview(trip_request)

    return TripPreviewResponse(
        data=preview,
        meta=ResponseMeta(),
    )


@router.post(
    "/generate",
    response_model=TripGenerationResponse,
    status_code=200,
    summary="生成旅行草案",
    description="调用大模型生成草案，并检查输出结构与旅行日期。",
    responses={
        422: {
            "model": ErrorResponse,
            "description": "请求参数校验失败。",
        },
        502: {
            "model": ErrorResponse,
            "description": "模型调用失败，或生成结果未通过校验。",
        },
        503: {
            "model": ErrorResponse,
            "description": "旅行生成服务尚未正确配置。",
        },
        504: {
            "model": ErrorResponse,
            "description": "模型请求超时。",
        },
    },
)
def generate_trip(
    trip_request: TripRequest,
    service: Annotated[
        TripGenerationService,
        Depends(
            get_trip_generation_service,
            scope="function",
        ),
    ],
) -> TripGenerationResponse:
    """根据合法旅行需求生成草案，并包装统一成功响应。"""

    draft = service.generate_draft(trip_request)

    return TripGenerationResponse(
        data=draft,
        meta=ResponseMeta(
            warnings=[
                "当前为 AI 旅行草案，具体地点、营业信息和路线尚未核实。"
            ],
        ),
    )


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    status_code=200,
    summary="生成附带天气的旅行规划",
    description=(
        "生成旅行草案，按日期附加天气和规则建议。"
        "天气查询失败时仍保留草案，并返回明确的降级状态。"
    ),
    responses={
        422: {
            "model": ErrorResponse,
            "description": "请求参数校验失败。",
        },
        502: {
            "model": ErrorResponse,
            "description": "模型调用失败，或草案未通过校验。",
        },
        503: {
            "model": ErrorResponse,
            "description": "旅行生成服务尚未正确配置。",
        },
        504: {
            "model": ErrorResponse,
            "description": "模型请求超时。",
        },
    },
)
def plan_trip(
    trip_request: TripPlanRequest,
    service: Annotated[
        TripPlanningService,
        Depends(get_trip_planning_service),
    ],
) -> TripPlanResponse:
    """调用规划服务，并将可选能力的状态整理为响应提醒。"""

    plan = service.create_plan(trip_request)

    warnings = [
        "活动由 AI 生成，具体地点、营业信息、路线和费用尚待核实。"
    ]

    if plan.weather_status == "skipped":
        warnings.append("本次按请求跳过天气查询。")

    elif plan.weather_status == "failed":
        warnings.append(
            "天气查询暂不可用，已保留旅行安排，请在出发前重新确认天气。"
        )

    elif plan.weather_coverage is not None:
        coverage = plan.weather_coverage

        if coverage.coverage_status == "partial":
            warnings.append(
                f"有 {len(coverage.missing_dates)} 天暂无预报，"
                "请在临近出行时重新查询。"
            )

        elif coverage.coverage_status == "none":
            warnings.append(
                "当前预报未覆盖旅行日期，请在临近出行时重新查询。"
            )

    return TripPlanResponse(
        data=plan,
        meta=ResponseMeta(warnings=warnings),
    )