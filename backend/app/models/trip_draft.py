"""定义旅行草案的输出结构与内部校验规则。"""

from datetime import date as Date
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.models.requests import MAX_TRIP_DAYS


# 用数字表达时段顺序，方便比较。
PERIOD_ORDER = {
    "morning": 0,
    "afternoon": 1,
    "evening": 2,
}


class ActivityDraft(BaseModel):
    """一个时段的活动建议。"""

    # 每一层模型都明确拒绝额外字段。
    # 字符串去除首尾空白后，再接受长度等校验。
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    period: Literal["morning", "afternoon", "evening"] = Field(
        description="活动时段：上午、下午或晚上。",
    )
    title: str = Field(
        min_length=1,
        max_length=80,
        description="活动建议的标题。",
    )
    description: str = Field(
        min_length=1,
        max_length=300,
        description="活动建议的说明，不代表已经核实的外部事实。",
    )


class DayDraft(BaseModel):
    """一天的主题和活动安排。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    # 使用 Date 作为导入别名，
    # 避免字段名 date 与日期类型名称混淆。
    #
    # 本阶段从 JSON 文本进行校验：
    # 严格日期字段允许 JSON 中的合法日期字符串，
    # 拒绝将数字等值自动解释为日期。
    date: Date = Field(
        strict=True,
        description="当天日期，JSON 中使用 YYYY-MM-DD。",
    )
    theme: str = Field(
        min_length=1,
        max_length=80,
        description="当天的主要游玩主题。",
    )
    activities: list[ActivityDraft] = Field(
        min_length=1,
        max_length=3,
        description="当天的活动建议，按上午、下午、晚上排列。",
    )

    @model_validator(mode="after")
    def validate_activity_periods(self) -> Self:
        """检查同一天的时段是否重复，以及顺序是否正确。"""
        periods = [
            activity.period
            for activity in self.activities
        ]

        # set 会去除重复值。
        # 去重后的数量减少，说明存在重复时段。
        if len(periods) != len(set(periods)):
            raise PydanticCustomError(
                "duplicate_activity_period",
                "同一天不能重复安排相同的活动时段",
            )

        positions = [
            PERIOD_ORDER[period]
            for period in periods
        ]

        # 已有顺序与升序排列不同，说明活动时段顺序错误。
        if positions != sorted(positions):
            raise PydanticCustomError(
                "activity_period_order_invalid",
                "活动必须按上午、下午、晚上顺序排列",
            )

        return self


class TripDraft(BaseModel):
    """整份旅行草案。

    本模型检查草案自身的结构和规则。
    与用户原始需求的对应关系，由后续服务层检查。
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    title: str = Field(
        min_length=1,
        max_length=100,
        description="旅行草案标题。",
    )
    summary: str = Field(
        min_length=1,
        max_length=600,
        description="旅行草案的总体说明。",
    )
    days: list[DayDraft] = Field(
        min_length=1,
        max_length=MAX_TRIP_DAYS,
        description="按日期排列的每日安排。",
    )

    @model_validator(mode="after")
    def validate_consecutive_dates(self) -> Self:
        """检查日期是否逐日递增，不允许重复、跳日或倒序。"""
        # days[1:] 表示从第二天开始的列表。
        # zip 将相邻两天配对：
        # 第一天与第二天、第二天与第三天……
        for previous_day, current_day in zip(
            self.days,
            self.days[1:],
        ):
            day_gap = (
                current_day.date - previous_day.date
            ).days

            if day_gap != 1:
                raise PydanticCustomError(
                    "draft_dates_not_consecutive",
                    "草案日期必须逐日递增，不能重复、跳日或倒序",
                )

        return self