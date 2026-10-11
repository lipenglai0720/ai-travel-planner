"""旅行规划相关的 API 路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.models.common import ResponseMeta
from app.models.errors import ErrorResponse
from app.models.requests import TripRequest
from app.models.trip import TripPreviewResponse
from app.services.trip_service import TripService


router = APIRouter(
    prefix="/trips",
    tags=["旅行规划"],
)


def get_trip_service() -> TripService:
    """创建本次接口调用使用的旅行服务。"""
    return TripService()


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