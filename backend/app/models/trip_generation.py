"""定义旅行草案生成接口的成功响应。"""

from pydantic import BaseModel, Field

from app.models.common import ResponseMeta
from app.models.trip_draft import TripDraft


class TripGenerationResponse(BaseModel):
    """旅行草案生成接口的成功响应。"""

    # 直接复用已经完成的草案模型。
    # API 层不再重新定义每日安排、活动时段等业务字段。
    data: TripDraft = Field(
        description="经过结构校验和请求一致性校验的旅行草案。",
    )

    # 沿用项目已有的公共响应元信息。
    meta: ResponseMeta = Field(
        description="响应标识与业务提醒。",
    )