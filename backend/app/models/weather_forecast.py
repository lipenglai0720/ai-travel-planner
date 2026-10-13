"""短期天气预报模型与日期覆盖检查。"""

from datetime import date
from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NaiveDatetime,
    model_validator,
)

from app.models.district import ADCODE_PATTERN
from app.models.weather import utc_now


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