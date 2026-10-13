"""短期预报查询输入与目标日期检查结果。"""

from datetime import date
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.weather import WeatherLookupQuery
from app.models.weather_forecast import (
    ForecastDay,
    WeatherForecast,
)


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