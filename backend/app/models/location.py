"""地点领域模型：行政区解析、POI 搜索和可信坐标记录。"""

from typing import Literal, TypeAlias

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.common import ApiResponse, utc_now


# 编码格式校验不代表编码实际存在，真实地区仍由高德查询确认。
ADCODE_PATTERN = r"^[0-9]{6}$"

# 省或直辖市级别的过滤编码。
PROVINCE_ADCODE_PATTERN = r"^[0-9]{2}0000$"


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


# 保留业务名称，实际复用同一个成功响应定义。
PoiSearchResponse: TypeAlias = ApiResponse[PoiSearchResult]
