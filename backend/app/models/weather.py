"""天气领域模型：实况、预报、日期覆盖和每日出行建议。"""

from datetime import date
from typing import Literal, Self, TypeAlias

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NaiveDatetime,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.models.common import (
    MAX_TRIP_DAYS,
    ApiResponse,
    calculate_day_count,
    utc_now,
)
from app.models.location import ADCODE_PATTERN, PROVINCE_ADCODE_PATTERN


class WeatherQuery(BaseModel):
    """发送天气请求前，先校验地区编码。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    adcode: str = Field(
        pattern=ADCODE_PATTERN,
        description="目标地区的六位行政区划编码。",
    )


class CurrentWeather(BaseModel):
    """经过校验的高德实况天气记录。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    province: str = Field(
        min_length=1,
        max_length=100,
        description="供应商返回的省份名称。",
    )

    city: str = Field(
        min_length=1,
        max_length=100,
        description="供应商返回的地区名称。",
    )

    adcode: str = Field(
        pattern=ADCODE_PATTERN,
        description="供应商返回的行政区划编码。",
    )

    weather: str = Field(
        min_length=1,
        max_length=100,
        description="天气现象，例如晴、多云或小雨。",
    )

    temperature_c: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="摄氏温度；缺失时为 None。",
    )

    humidity_percent: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="相对湿度百分比；缺失时为 None。",
    )

    wind_direction: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="风向描述；缺失时为 None。",
    )

    # 风力可能是描述或区间，因此保留为字符串。
    wind_power: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="风力级别描述；缺失时为 None。",
    )

    reported_at: NaiveDatetime = Field(
        description="供应商发布时间，保留未带时区的含义。",
    )

    reported_at_timezone: Literal[
        "not_provided"
    ] = "not_provided"

    queried_at: AwareDatetime = Field(
        default_factory=utc_now,
        description="本次查询完成时间，使用 UTC。",
    )

    source: Literal["amap"] = "amap"

    # 表示调用的是供应商的实况天气接口。
    # 不代表已经检查过数据是否足够新。
    data_kind: Literal[
        "current_conditions"
    ] = "current_conditions"


class WeatherLookupQuery(BaseModel):
    """按城市或区县查询天气的业务输入。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    city: str = Field(
        min_length=1,
        max_length=50,
        description="城市、区县名称，也可以填写六位 adcode。",
    )

    province_adcode: str | None = Field(
        default=None,
        pattern=PROVINCE_ADCODE_PATTERN,
        description="可选的省或直辖市编码，用于缩小行政区查询范围。",
    )


class ForecastDay(BaseModel):
    """供应商提供的某一天预报。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    forecast_date: date = Field(
        description="这条预报对应的日期。",
    )

    day_weather: str = Field(
        min_length=1,
        max_length=100,
        description="白天天气现象。",
    )

    night_weather: str = Field(
        min_length=1,
        max_length=100,
        description="夜间天气现象。",
    )

    day_temperature_c: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="白天温度，单位为摄氏度。",
    )

    night_temperature_c: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="夜间温度，单位为摄氏度。",
    )

    day_wind_direction: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="白天风向。",
    )

    night_wind_direction: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="夜间风向。",
    )

    day_wind_power: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="白天风力描述。",
    )

    night_wind_power: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="夜间风力描述。",
    )


class WeatherForecast(BaseModel):
    """一个地区本次查询得到的短期天气预报。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    province: str = Field(
        min_length=1,
        max_length=100,
    )

    city: str = Field(
        min_length=1,
        max_length=100,
    )

    adcode: str = Field(
        pattern=ADCODE_PATTERN,
    )

    reported_at: NaiveDatetime = Field(
        description="供应商预报发布时间，保留未带时区的含义。",
    )

    reported_at_timezone: Literal[
        "not_provided"
    ] = "not_provided"

    queried_at: AwareDatetime = Field(
        default_factory=utc_now,
        description="本次查询完成时间，使用 UTC。",
    )

    source: Literal["amap"] = "amap"

    # 明确标记数据属于供应商预报。
    data_kind: Literal["forecast"] = "forecast"

    days: list[ForecastDay] = Field(
        min_length=1,
        description="按日期升序排列的实际预报记录。",
    )

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        """校验整个预报日期集合。"""

        dates = [
            item.forecast_date
            for item in self.days
        ]

        # set 会去掉重复日期。
        # 数量不相同，说明原列表存在重复日期。
        if len(dates) != len(set(dates)):
            raise ValueError("预报日期不能重复。")

        if dates != sorted(dates):
            raise ValueError("预报记录必须按日期升序排列。")

        return self

    def find_day(
        self,
        target_date: date,
    ) -> ForecastDay | None:
        """查找指定日期的记录。

        返回：
            找到时返回 ForecastDay。
            没有记录时返回 None。
        """

        for item in self.days:
            if item.forecast_date == target_date:
                return item

        return None


class ForecastLookupQuery(WeatherLookupQuery):
    """复用地区查询条件，并增加可选目标日期。"""

    target_date: date | None = Field(
        default=None,
        description="可选的目标日期，格式为 YYYY-MM-DD。",
    )

    @field_validator("target_date", mode="before")
    @classmethod
    def parse_target_date(cls, value: object) -> object:
        """显式解析 URL 中的日期文本，再交给严格类型校验。"""

        # Python 代码直接传入 date 或 None 时，
        # 继续交给 Pydantic 检查字段类型。
        if not isinstance(value, str):
            return value

        text = value.strip()
        parsed = date.fromisoformat(text)

        # 只接受当前接口约定的 YYYY-MM-DD 格式。
        if parsed.isoformat() != text:
            raise ValueError("目标日期应使用 YYYY-MM-DD。")

        return parsed


class ForecastLookupResult(BaseModel):
    """完整预报与一个目标日期的检查结果。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    forecast: WeatherForecast = Field(
        description="供应商实际返回并经过校验的完整短期预报。",
    )

    target_date: date | None = Field(
        default=None,
        description="本次请求的目标日期。",
    )

    coverage_status: Literal[
        "not_requested",
        "available",
        "unavailable",
    ] = Field(
        description="目标日期的预报覆盖状态。",
    )

    selected_day: ForecastDay | None = Field(
        default=None,
        description="目标日期对应的记录；没有记录时为 None。",
    )

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        """保证覆盖状态和选中记录与完整预报一致。"""

        if self.target_date is None:
            expected_day = None
            expected_status = "not_requested"
        else:
            expected_day = self.forecast.find_day(
                self.target_date
            )

            expected_status = (
                "available"
                if expected_day is not None
                else "unavailable"
            )

        if (
            self.coverage_status != expected_status
            or self.selected_day != expected_day
        ):
            raise ValueError(
                "日期覆盖状态或选中记录与实际预报不一致。"
            )

        return self


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


# 只为不同业务数据绑定类型，不再重复声明 data 和 meta。
WeatherCurrentResponse: TypeAlias = ApiResponse[CurrentWeather]
WeatherForecastResponse: TypeAlias = ApiResponse[ForecastLookupResult]
WeatherForecastRangeResponse: TypeAlias = ApiResponse[TripWeatherResult]
