"""旅行 API 路由：接收请求、调用业务服务并包装响应。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.models.common import ResponseMeta
from app.models.requests import TripRequest
from app.models.trip import TripPreviewResponse
from app.services.trip_service import TripService


# 当前模块中的接口统一使用 /trips 前缀。
# tags 用于在 /docs 中将接口分组。
router = APIRouter(
    prefix="/trips",
    tags=["旅行规划"],
)


def get_trip_service() -> TripService:
    """为路由提供业务服务对象。"""

    # 依赖函数负责构造对象。
    # 具体的业务处理由路由调用服务方法执行。
    return TripService()


@router.post(
    "/preview",
    response_model=TripPreviewResponse,
    status_code=200,
    summary="预览旅行需求",
    description="校验旅行输入并返回日期、人数和预算摘要。",
)
def preview_trip(
    trip_request: TripRequest,
    service: Annotated[TripService, Depends(get_trip_service)],
) -> TripPreviewResponse:
    """接收旅行请求，返回结构明确的需求预览响应。"""

    preview = service.preview(trip_request)

    return TripPreviewResponse(
        data=preview,
        meta=ResponseMeta(),
    )