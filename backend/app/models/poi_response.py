"""定义 POI 查询接口的成功响应。"""

from pydantic import BaseModel, Field

from app.models.common import ResponseMeta
from app.models.poi import PoiSearchResult


class PoiSearchResponse(BaseModel):
    """地点查询接口的成功响应。"""

    # 复用客户端返回的业务结果。
    # 其中包含查询条件、数据来源、查询时间和 POI 列表。
    data: PoiSearchResult = Field(
        description="经过格式转换和校验的候选地点查询结果。",
    )

    meta: ResponseMeta = Field(
        description="响应标识和业务提醒。",
    )