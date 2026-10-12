"""行政区查询条件与经过校验的解析结果。"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
)


# 本项目把 adcode 作为六位 ASCII 数字字符串保存。
# 格式正确不代表这个编码一定存在；实际记录必须来自高德。
ADCODE_PATTERN = r"^[0-9]{6}$"

# 本节的 filter 只接受省或直辖市级别的编码形式。
# 这是查询范围的输入约束，不是全国行政区编码表。
PROVINCE_ADCODE_PATTERN = r"^[0-9]{2}0000$"


def utc_now() -> datetime:
    """返回带有 UTC 时区信息的当前时间。"""
    return datetime.now(timezone.utc)


class DistrictQuery(BaseModel):
    """调用行政区域接口前，先校验查询条件。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    keyword: str = Field(
        min_length=1,
        max_length=50,
        description="完整行政区名称、城市简称或六位 adcode。",
    )

    province_adcode: str | None = Field(
        default=None,
        pattern=PROVINCE_ADCODE_PATTERN,
        description="可选的省或直辖市编码，用于缩小查询范围。",
    )


class DistrictInfo(BaseModel):
    """只保留项目需要的行政区字段。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    name: str = Field(
        min_length=1,
        max_length=100,
        description="高德返回的行政区正式名称。",
    )

    adcode: str = Field(
        pattern=ADCODE_PATTERN,
        description="高德返回的行政区划编码。",
    )

    level: Literal[
        "country",
        "province",
        "city",
        "district",
        "street",
    ] = Field(
        description="高德返回的行政级别。",
    )


class DistrictResult(BaseModel):
    """从候选记录中解析出的一个明确行政区。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    keyword: str = Field(
        min_length=1,
        max_length=50,
    )

    province_adcode: str | None = Field(
        default=None,
        pattern=PROVINCE_ADCODE_PATTERN,
    )

    region: DistrictInfo

    source: Literal["amap"] = "amap"

    # 记录本次查询完成的时间。
    # 这不是行政区资料本身的更新时间。
    queried_at: AwareDatetime = Field(
        default_factory=utc_now,
    )