"""旅行领域模型：需求、预览、AI 草案和附加天气的规划结果。"""

from datetime import date
from datetime import date as Date
from typing import Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.models.common import (
    MAX_TRIP_DAYS,
    ApiResponse,
    calculate_day_count,
)
from app.models.location import PROVINCE_ADCODE_PATTERN
from app.models.weather import DailyWeatherItem, ForecastRangeResult


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
        """校验跨字段规则，并为错误附加原因标识和字段信息。"""

        # mode="after" 表示各字段已完成基本校验。
        # 此时 start_date 和 end_date 已经是 Python 的 date 对象，
        # 因此可以直接比较日期先后。
        if self.end_date < self.start_date:
            raise PydanticCustomError(
                "date_order_invalid",
                "结束日期不能早于开始日期",
                {"field": "end_date"},
            )

        # 继续使用之前的日期计算函数，包含开始日和结束日。
        day_count = calculate_day_count(
            self.start_date,
            self.end_date,
        )

        if day_count > MAX_TRIP_DAYS:
            raise PydanticCustomError(
                "trip_too_long",
                f"旅行天数不能超过 {MAX_TRIP_DAYS} 天",
                {"field": "end_date"},
            )

        if self.room_count > self.travelers:
            raise PydanticCustomError(
                "room_count_exceeds_travelers",
                "房间数不能超过出行人数",
                {"field": "room_count"},
            )

        # 校验通过后，返回当前模型实例。
        return self

    @property
    def day_count(self) -> int:
        """根据起止日期计算旅行天数，供其他模块读取。"""

        return calculate_day_count(
            self.start_date,
            self.end_date,
        )


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


# 用数字表达活动时段顺序，供每日草案校验使用。
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


# 天气查询的执行状态，与预报日期覆盖状态分别表达。
WeatherFetchStatus = Literal["loaded", "failed", "skipped"]


class TripPlanRequest(TripRequest):
    """复用旅行需求，并增加新接口的控制参数。"""

    province_adcode: str | None = Field(
        default=None,
        pattern=PROVINCE_ADCODE_PATTERN,
        description="可选的省或直辖市编码，用于明确目的地区域。",
    )

    include_weather: bool = Field(
        default=True,
        strict=True,
        description="是否查询并附加天气，默认开启。",
    )


class PlannedDay(DayDraft):
    """在已有每日活动安排上附加天气与建议。"""

    weather: DailyWeatherItem = Field(
        description="与当天日期对应的天气记录和出行建议。",
    )

    @model_validator(mode="after")
    def validate_weather_date(self) -> Self:
        """保证行程日期与天气日期一致。"""

        if self.weather.travel_date != self.date:
            raise ValueError("行程日期与天气日期不一致。")

        if self.weather.forecast is None:
            if self.weather.availability != "unavailable":
                raise ValueError("缺少预报时，天气状态必须为 unavailable。")

        else:
            if (
                self.weather.availability != "available"
                or self.weather.forecast.forecast_date != self.date
            ):
                raise ValueError("预报记录与当天行程不一致。")

        return self


class TripPlan(BaseModel):
    """整合每日安排与天气后的旅行规划结果。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    title: str = Field(
        min_length=1,
        max_length=100,
        description="旅行规划标题。",
    )

    summary: str = Field(
        min_length=1,
        max_length=600,
        description="旅行规划总体说明。",
    )

    days: list[PlannedDay] = Field(
        min_length=1,
        max_length=MAX_TRIP_DAYS,
        description="按日期排列的每日活动、天气和建议。",
    )

    weather_status: WeatherFetchStatus = Field(
        description="天气查询执行状态。",
    )

    weather_coverage: ForecastRangeResult | None = Field(
        default=None,
        description="查询成功时的覆盖结果；失败或跳过时为 null。",
    )

    weather_error_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="天气查询失败时的稳定错误标识。",
    )

    suggestion_source: Literal["project_rules"] = Field(
        default="project_rules",
        description="天气出行建议的来源。",
    )

    @model_validator(mode="after")
    def validate_weather_state(self) -> Self:
        """保证查询状态、覆盖结果和错误标识一致。"""

        if self.weather_status == "loaded":
            if (
                self.weather_coverage is None
                or self.weather_error_code is not None
            ):
                raise ValueError("天气查询成功时必须提供覆盖结果。")

        elif self.weather_coverage is not None:
            raise ValueError("天气查询失败或跳过时不能提供覆盖结果。")

        if self.weather_status == "failed":
            if self.weather_error_code is None:
                raise ValueError("天气查询失败时必须提供错误标识。")

        elif self.weather_error_code is not None:
            raise ValueError("只有天气查询失败时才能提供错误标识。")

        if (
            self.weather_status != "loaded"
            and any(
                day.weather.forecast is not None
                for day in self.days
            )
        ):
            raise ValueError("天气查询失败或跳过时不能附加预报记录。")

        return self


# 保留原有业务响应名称，减少调用代码的迁移成本。
TripPreviewResponse: TypeAlias = ApiResponse[TripPreview]
TripGenerationResponse: TypeAlias = ApiResponse[TripDraft]
TripPlanResponse: TypeAlias = ApiResponse[TripPlan]
