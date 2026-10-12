"""实况天气查询条件与规范化天气模型。"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NaiveDatetime,
)

from app.models.district import (
    ADCODE_PATTERN,
    PROVINCE_ADCODE_PATTERN,
)

def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(timezone.utc)


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