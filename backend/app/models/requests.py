"""旅行请求模型：定义输入字段、跨字段规则及旅行天数计算。"""

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


# 按总体开发文档，初版最多支持 7 天旅行。
# 将上限集中定义在这里，避免在多个位置重复写数字。
MAX_TRIP_DAYS = 7


def calculate_day_count(start_date: date, end_date: date) -> int:
    """计算包含开始日和结束日的旅行天数。

    参数：
        start_date：已经解析完成的开始日期。
        end_date：已经解析完成的结束日期。

    返回：
        包含首尾两天的旅行天数。

    异常：
        结束日期早于开始日期时，抛出 ValueError。
    """

    # 必须先检查日期顺序，避免产生 0 天或负数天数。
    if end_date < start_date:
        raise ValueError("结束日期不能早于开始日期")

    # 两个 date 对象相减，得到 timedelta。
    # .days 取得相差的天数；加 1 后包含开始日和结束日。
    return (end_date - start_date).days + 1


class TripRequest(BaseModel):
    """旅行规划请求；执行字段校验和跨字段业务校验。"""

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

    @model_validator(mode="after")
    def validate_trip_rules(self) -> Self:
        """在字段校验完成后，检查多个字段之间的业务关系。"""

        # 此时 start_date 和 end_date 已经是 date 对象。
        # 日期倒置时，计算函数会抛出 ValueError。
        day_count = calculate_day_count(
            self.start_date,
            self.end_date,
        )

        if day_count > MAX_TRIP_DAYS:
            raise ValueError(
                f"旅行天数不能超过 {MAX_TRIP_DAYS} 天"
            )

        # 初版按出行人员使用的房间进行预算估算。
        # 在该产品规则下，房间数不得超过出行人数。
        if self.room_count > self.travelers:
            raise ValueError("房间数不能超过出行人数")

        # after 模型校验器必须返回通过校验的模型对象。
        return self

    @property
    def day_count(self) -> int:
        """根据起止日期计算旅行天数，供其他模块读取。"""

        return calculate_day_count(
            self.start_date,
            self.end_date,
        )