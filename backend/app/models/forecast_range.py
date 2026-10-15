"""旅行日期区间、预报覆盖及每日天气建议模型。"""

from datetime import date
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.models.district import PROVINCE_ADCODE_PATTERN
from app.models.requests import (
    MAX_TRIP_DAYS,
    calculate_day_count,
)
from app.models.weather_forecast import (
    ForecastDay,
    WeatherForecast,
)


ForecastCoverageStatus = Literal["full", "partial", "none"]


class ForecastDateRange(BaseModel):
    """需要检查预报覆盖情况的旅行日期区间。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    start_date: date = Field(
        description="旅行开始日期，格式为 YYYY-MM-DD。",
    )

    end_date: date = Field(
        description="旅行结束日期，格式为 YYYY-MM-DD。",
    )

    @field_validator(
        "start_date",
        "end_date",
        mode="before",
    )
    @classmethod
    def parse_date(cls, value: object) -> object:
        """显式解析日期字符串，再执行严格类型校验。"""

        if not isinstance(value, str):
            return value

        text = value.strip()
        parsed = date.fromisoformat(text)

        # 明确限制接口使用 YYYY-MM-DD 日期格式。
        if parsed.isoformat() != text:
            raise ValueError("日期应使用 YYYY-MM-DD 格式。")

        return parsed

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """检查日期顺序和旅行天数。"""

        if self.end_date < self.start_date:
            raise PydanticCustomError(
                "date_order_invalid",
                "结束日期不能早于开始日期",
                {"field": "end_date"},
            )

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

        return self

    @property
    def day_count(self) -> int:
        """返回包含开始日和结束日的旅行天数。"""

        return calculate_day_count(
            self.start_date,
            self.end_date,
        )


class ForecastRangeQuery(ForecastDateRange):
    """区间天气接口的查询参数。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    # 继承父类的起止日期、日期解析和旅行长度校验，
    # 再增加地区查询条件。
    city: str = Field(
        min_length=1,
        max_length=50,
        description="城市、区县名称，也可以填写六位 adcode。",
    )

    province_adcode: str | None = Field(
        default=None,
        pattern=PROVINCE_ADCODE_PATTERN,
        description="可选的省或直辖市编码。",
    )


class ForecastRangeResult(BaseModel):
    """旅行日期区间的预报覆盖结果。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    forecast: WeatherForecast
    date_range: ForecastDateRange
    coverage_status: ForecastCoverageStatus

    covered_dates: list[date]
    missing_dates: list[date]


class DailyWeatherItem(BaseModel):
    """某个旅行日期的天气记录与出行建议。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    travel_date: date = Field(
        description="对应的旅行日期。",
    )

    availability: Literal["available", "unavailable"] = Field(
        description="该旅行日期是否存在预报记录。",
    )

    forecast: ForecastDay | None = Field(
        default=None,
        description="供应商该日预报；没有记录时为 null。",
    )

    suggestions: list[str] = Field(
        min_length=1,
        description="根据预报和项目规则生成的出行建议。",
    )

    missing_fields: list[str] = Field(
        default_factory=list,
        description="已有预报记录中缺少的可选字段名称。",
    )


class TripWeatherResult(BaseModel):
    """一次旅行的区间预报、每日天气和建议。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    coverage: ForecastRangeResult = Field(
        description="旅行日期区间的预报覆盖结果。",
    )

    daily_weather: list[DailyWeatherItem] = Field(
        min_length=1,
        max_length=MAX_TRIP_DAYS,
        description="按旅行日期升序排列的每日天气结果。",
    )

    suggestion_source: Literal["project_rules"] = Field(
        default="project_rules",
        description="出行建议来源，当前使用项目规则。",
    )