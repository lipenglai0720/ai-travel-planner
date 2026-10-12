"""旅行规划相关的 API 路由。"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings
from app.llm.client import create_trip_chat_model
from app.models.common import ResponseMeta
from app.models.errors import ErrorResponse
from app.models.requests import TripRequest
from app.models.trip import TripPreviewResponse
from app.models.trip_generation import TripGenerationResponse
from app.services.trip_generation_service import TripGenerationService
from app.services.trip_service import TripService


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