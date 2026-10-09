"""旅行相关的请求模型：定义用户输入字段及其校验规则。"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TripRequest(BaseModel):
    """旅行规划请求；当前版本执行各字段的类型和范围校验。"""

    model_config = ConfigDict(
        # 拒绝模型中未定义的字段，便于发现客户端字段拼写错误。
        extra="forbid",

        # 去除普通字符串字段首尾的空白。
        # 例如，目的地 " 北京 " 会被规范化为 "北京"。
        str_strip_whitespace=True,
    )

    # 没有提供 default，因此 destination 是必填字段。
    # 当前检查文本格式，真实城市的确认由后续地图服务负责。
    destination: str = Field(
        min_length=1,
        max_length=50,
        description="目的地城市名称。",
    )

    # 输入约定使用 YYYY-MM-DD，例如 "2026-11-01"。
    # Pydantic 会把可解析的日期输入转换为 Python date 对象。
    start_date: date = Field(
        description="旅行开始日期。",
    )

    end_date: date = Field(
        description="旅行结束日期。",
    )

    # strict=True 要求输入本身就是整数。
    # 拒绝 True、"2"、2.0 等值作为出行人数。
    travelers: int = Field(
        strict=True,
        ge=1,
        le=20,
        description="出行人数，支持 1～20 人。",
    )

    # 金额以整数分表示，避免直接使用浮点数累计金额。
    # 这是所有出行人员合计的总预算。
    budget_cents: int = Field(
        strict=True,
        gt=0,
        description="旅行总预算，单位为人民币分。",
    )

    # Literal 列出允许使用的固定值。
    # 前端以后将中文选项映射为这些值，再发送给后端。
    transportation: Literal[
        "public_transit",
        "driving",
        "walking",
    ] = Field(
        default="public_transit",
        description="市内交通偏好：公共交通、自驾或步行。",
    )

    accommodation_preference: Literal[
        "economy",
        "comfort",
        "luxury",
    ] = Field(
        default="economy",
        description="住宿偏好：经济型、舒适型或高档型。",
    )

    room_count: int = Field(
        default=1,
        strict=True,
        ge=1,
        le=20,
        description="希望预订的房间数，支持 1～20 间。",
    )

    # default_factory=list 会为每个请求创建自己的空列表。
    # 此处 max_length 限制列表项数，list[str] 约束元素类型。
    preferences: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="兴趣偏好列表，例如历史文化、美食、自然风光。",
    )

    pace: Literal[
        "relaxed",
        "balanced",
        "intensive",
    ] = Field(
        default="relaxed",
        description="游玩节奏：轻松、均衡或紧凑。",
    )