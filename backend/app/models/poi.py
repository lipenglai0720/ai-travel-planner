"""定义 POI 查询输入、规范化地点数据和查询结果。"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
)


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(timezone.utc)


class PoiSearchQuery(BaseModel):
    """已经校验的 POI 搜索条件。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    # 长度限制是本项目当前的输入约定。
    city: str = Field(
        min_length=1,
        max_length=50,
        description="城市名称、citycode 或 adcode。",
    )

    keyword: str = Field(
        min_length=1,
        max_length=80,
        description="一个地点搜索关键词。",
    )


class Poi(BaseModel):
    """经过格式转换与校验的地点记录。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    poi_id: str = Field(
        min_length=1,
        max_length=100,
        description="高德返回的 POI 标识。",
    )

    name: str = Field(
        min_length=1,
        max_length=200,
        description="高德返回的地点名称。",
    )

    # None 表示外部服务没有提供地址。
    # 不使用虚构地址填补这个字段。
    address: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="地点地址；未提供时为 None。",
    )

    longitude: float = Field(
        ge=-180,
        le=180,
        allow_inf_nan=False,
        description="经度，必须是范围内的有限数值。",
    )

    latitude: float = Field(
        ge=-90,
        le=90,
        allow_inf_nan=False,
        description="纬度，必须是范围内的有限数值。",
    )


class PoiSearchResult(BaseModel):
    """一次 POI 查询的业务结果。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    city: str = Field(
        min_length=1,
        max_length=50,
    )

    keyword: str = Field(
        min_length=1,
        max_length=80,
    )

    source: Literal["amap"] = "amap"

    coordinate_system: Literal["GCJ-02"] = "GCJ-02"

    # 每次创建结果对象时调用 utc_now。
    # 这个时间表示查询结果被本项目接收和处理的时间，
    # 不表示景点信息本身的更新时间。
    queried_at: AwareDatetime = Field(
        default_factory=utc_now,
    )

    # 空列表是合法的搜索结果。
    pois: list[Poi] = Field(
        default_factory=list,
    )