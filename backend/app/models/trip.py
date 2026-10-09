"""旅行业务结果模型：定义需求预览的数据与响应结构。"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.models.common import ResponseMeta
from app.models.requests import MAX_TRIP_DAYS


class TripPreview(BaseModel):
    """经过校验的旅行需求摘要。"""

    destination: str = Field(
        min_length=1,
        max_length=50,
        description="用户提交的目的地名称。",
    )

    start_date: date = Field(
        description="旅行开始日期。",
    )

    end_date: date = Field(
        description="旅行结束日期。",
    )

    day_count: int = Field(
        strict=True,
        ge=1,
        le=MAX_TRIP_DAYS,
        description="由起止日期计算的旅行天数。",
    )

    travelers: int = Field(
        strict=True,
        ge=1,
        le=20,
        description="出行人数。",
    )

    room_count: int = Field(
        strict=True,
        ge=1,
        le=20,
        description="用户希望预订的房间数。",
    )

    # 明确表示这是用户提出的预算。
    # 后续的费用估算将使用其他字段表示。
    requested_budget_cents: int = Field(
        strict=True,
        gt=0,
        description="用户提出的旅行总预算，单位为人民币分。",
    )

    currency: Literal["CNY"] = Field(
        default="CNY",
        description="预算币种，当前使用人民币。",
    )


class TripPreviewResponse(BaseModel):
    """旅行需求预览接口的成功响应。"""

    data: TripPreview = Field(
        description="旅行需求摘要。",
    )

    meta: ResponseMeta = Field(
        description="响应元信息。",
    )