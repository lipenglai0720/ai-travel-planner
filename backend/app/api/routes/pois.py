"""地点查询相关的 API 路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings
from app.models.common import (
    ErrorResponse,
    ResponseMeta,
)
from app.models.location import (
    PoiSearchQuery,
    PoiSearchResponse,
)
from app.services.poi_service import PoiService


router = APIRouter(
    prefix="/pois",
    tags=["地点查询"],
)


def get_poi_service() -> PoiService:
    """创建本次请求使用的地点查询服务。"""

    settings = Settings()

    # 服务构造时只保存配置。
    # 高德客户端将在 service.search() 中创建。
    return PoiService(
        api_key=settings.amap_web_api_key,
        timeout_seconds=settings.amap_timeout_seconds,
    )


@router.get(
    "/search",
    response_model=PoiSearchResponse,
    status_code=200,
    summary="搜索候选地点",
    description="按城市和关键词查询高德地点，返回经过校验的数据。",
    responses={
        422: {
            "model": ErrorResponse,
            "description": "查询参数校验失败。",
        },
        502: {
            "model": ErrorResponse,
            "description": "高德调用失败，或返回数据不合格。",
        },
        503: {
            "model": ErrorResponse,
            "description": "地点查询服务配置不正确。",
        },
        504: {
            "model": ErrorResponse,
            "description": "高德请求超时。",
        },
    },
)
def search_pois(
    query: Annotated[
        PoiSearchQuery,
        Query(),
    ],
    service: Annotated[
        PoiService,
        Depends(get_poi_service),
    ],
) -> PoiSearchResponse:
    """调用服务搜索候选地点，并包装统一成功响应。"""

    result = service.search(query)

    warnings = [
        "搜索结果是候选地点，目标匹配及营业状态仍需核实。"
    ]

    if not result.pois:
        warnings.append(
            "本次查询未找到匹配地点，请调整城市或关键词。"
        )

    return PoiSearchResponse(
        data=result,
        meta=ResponseMeta(
            warnings=warnings,
        ),
    )
