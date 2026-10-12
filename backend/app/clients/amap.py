"""调用高德服务，并转换为项目业务模型。"""

from typing import Any

import httpx
from pydantic import SecretStr

from app.models.district import (
    DistrictInfo,
    DistrictQuery,
    DistrictResult,
)
from app.models.poi import (
    Poi,
    PoiSearchQuery,
    PoiSearchResult,
)
from datetime import datetime

from app.models.weather import (
    CurrentWeather,
    WeatherQuery,
)

AMAP_SEARCH_URL = "https://restapi.amap.com/v3/place/text"
AMAP_DISTRICT_URL = "https://restapi.amap.com/v3/config/district"
AMAP_WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"

DISTRICT_PAGE_SIZE = 20

# 高德把直辖市放在 province 级别。
# 这里的名称集合用于判断支持的行政级别。
# 实际 adcode 始终读取高德响应，不从这里生成。
MUNICIPALITY_NAMES = {
    "北京市",
    "天津市",
    "上海市",
    "重庆市",
}


class AmapError(RuntimeError):
    """高德客户端能够明确识别的失败。"""

    def __init__(
        self,
        code: str,
        message: str,
        provider_code: str | None = None,
    ) -> None:
        """保存项目错误标识及可选的高德错误码。"""
        super().__init__(message)
        self.code = code
        self.provider_code = provider_code


def _parse_poi(raw: object) -> Poi:
    """把一条高德原始记录转换为经过校验的 Poi。"""

    if not isinstance(raw, dict):
        raise ValueError("POI 记录应为对象。")

    location = raw.get("location")

    if not isinstance(location, str):
        raise ValueError("坐标应为字符串。")

    parts = location.split(",")

    if len(parts) != 2:
        raise ValueError("坐标应包含经度和纬度。")

    # 高德坐标顺序为：经度在前，纬度在后。
    longitude = float(parts[0].strip())
    latitude = float(parts[1].strip())

    raw_address = raw.get("address")

    if raw_address is None or raw_address == []:
        address = None
    elif isinstance(raw_address, str):
        address = raw_address.strip() or None
    else:
        raise ValueError("地址类型不符合预期。")

    return Poi(
        poi_id=raw.get("id"),
        name=raw.get("name"),
        address=address,
        longitude=longitude,
        latitude=latitude,
    )


def _parse_district(raw: object) -> DistrictInfo:
    """从一条原始行政区记录中挑选并校验必要字段。"""

    if not isinstance(raw, dict):
        raise ValueError("行政区记录应为对象。")

    # 不把外部服务的全部字段直接传入业务模型。
    # citycode、center、子级 districts 等字段当前无需使用。
    return DistrictInfo(
        name=raw.get("name"),
        adcode=raw.get("adcode"),
        level=raw.get("level"),
    )

def _optional_weather_number(raw: object) -> float | None:
    """将可选数值转换为 float，明确区分缺失和损坏。

    项目约定：
        None、空字符串、纯空白字符串、空数组视为缺失。

        数字字符串和 JSON 数字允许显式转换。

        布尔值、非空数组、对象等类型不接受。
    """

    if raw is None or raw == []:
        return None

    # bool 需要先排除，避免 True 被转换成 1.0。
    if isinstance(raw, bool):
        raise ValueError("天气数值不能是布尔值。")

    if isinstance(raw, (int, float)):
        return float(raw)

    if isinstance(raw, str):
        value = raw.strip()

        if not value:
            return None

        return float(value)

    raise ValueError("天气数值类型不符合要求。")


def _optional_weather_text(raw: object) -> str | None:
    """规范化可选的风向、风力描述。"""

    if raw is None or raw == []:
        return None

    if not isinstance(raw, str):
        raise ValueError("天气描述应为字符串。")

    return raw.strip() or None


def _parse_weather_report_time(raw: object) -> datetime:
    """校验并解析供应商的发布时间，不补充未经确认的时区。"""

    if not isinstance(raw, str):
        raise ValueError("天气发布时间应为字符串。")

    value = raw.strip()
    time_format = "%Y-%m-%d %H:%M:%S"

    # strptime 同时检查日期是否存在。
    # 例如 2026-02-30 会抛出 ValueError。
    parsed = datetime.strptime(
        value,
        time_format,
    )

    # 限定为当前适配器接受的标准格式。
    if parsed.strftime(time_format) != value:
        raise ValueError("天气发布时间格式不符合要求。")

    return parsed


def _parse_current_weather(raw: object) -> CurrentWeather:
    """将一条高德实况天气记录转换为业务模型。"""

    if not isinstance(raw, dict):
        raise ValueError("实况天气记录应为对象。")

    # 显式挑选和转换字段。
    # 外部服务新增的其他字段不会直接进入业务模型。
    return CurrentWeather(
        province=raw.get("province"),
        city=raw.get("city"),
        adcode=raw.get("adcode"),
        weather=raw.get("weather"),
        temperature_c=_optional_weather_number(
            raw.get("temperature")
        ),
        humidity_percent=_optional_weather_number(
            raw.get("humidity")
        ),
        wind_direction=_optional_weather_text(
            raw.get("winddirection")
        ),
        wind_power=_optional_weather_text(
            raw.get("windpower")
        ),
        reported_at=_parse_weather_report_time(
            raw.get("reporttime")
        ),
    )
class AmapClient:
    """管理高德 HTTP 调用和返回数据转换。"""

    def __init__(
        self,
        api_key: SecretStr | None,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """创建客户端，但暂不发送请求。

        参数：
            api_key：
                高德 Web 服务 Key，通常来自 Settings。

            timeout_seconds：
                传给 HTTPX 的超时参数。

            transport：
                正常调用使用默认传输。
                测试可以注入 MockTransport。
        """

        key_value = (
            api_key.get_secret_value().strip()
            if api_key is not None
            else ""
        )

        if not key_value:
            raise AmapError(
                code="amap_not_configured",
                message="没有配置有效的高德 Web 服务 Key。",
            )

        self._api_key = key_value

        try:
            self._http_client = httpx.Client(
                timeout=timeout_seconds,
                transport=transport,
                follow_redirects=False,
            )
        except ValueError:
            raise AmapError(
                code="amap_configuration_invalid",
                message="HTTP 客户端配置无效，请检查代理等配置。",
            ) from None

    def close(self) -> None:
        """关闭本客户端管理的 HTTP 连接资源。"""
        self._http_client.close()

    def _request_json(
        self,
        url: str,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        """发送 GET 请求，完成两个接口共有的基础检查。

        返回值仍是外部 JSON 字典。
        POI 或行政区的具体字段由各自方法继续校验。
        """

        try:
            response = self._http_client.get(
                url,
                params=params,
            )
            response.raise_for_status()

        except httpx.TimeoutException:
            raise AmapError(
                code="amap_timeout",
                message="高德请求超时，请稍后重试。",
            ) from None

        except httpx.HTTPStatusError as exc:
            # 不输出完整 HTTP 异常，避免暴露含 Key 的 URL。
            raise AmapError(
                code="amap_http_error",
                message=(
                    "高德返回 HTTP "
                    f"{exc.response.status_code}。"
                ),
            ) from None

        except httpx.RequestError:
            raise AmapError(
                code="amap_connection_error",
                message="高德请求未能完成，请检查网络和代理。",
            ) from None

        try:
            payload = response.json()
        except ValueError:
            raise AmapError(
                code="amap_response_invalid",
                message="高德响应不是有效 JSON。",
            ) from None

        if not isinstance(payload, dict):
            raise AmapError(
                code="amap_response_invalid",
                message="高德响应最外层应为对象。",
            )

        status = payload.get("status")

        # HTTP 200 不代表高德业务一定成功。
        if status == "0":
            raw_code = payload.get("infocode")

            provider_code = (
                raw_code
                if (
                    isinstance(raw_code, str)
                    and len(raw_code) == 5
                    and raw_code.isdecimal()
                )
                else None
            )

            raise AmapError(
                code="amap_business_error",
                message="高德业务请求失败，请检查错误码和服务配置。",
                provider_code=provider_code,
            )

        if status != "1":
            raise AmapError(
                code="amap_response_invalid",
                message="高德业务状态字段不符合预期。",
            )

        return payload

    def search_pois(
        self,
        query: PoiSearchQuery,
    ) -> PoiSearchResult:
        """搜索候选地点，返回经过校验的业务结果。"""

        params = {
            "key": self._api_key,
            "city": query.city,
            "keywords": query.keyword,
            "citylimit": "true",
            "offset": 5,
            "page": 1,
            "extensions": "base",
            "output": "JSON",
        }

        payload = self._request_json(
            AMAP_SEARCH_URL,
            params,
        )

        raw_pois = payload.get("pois")

        if not isinstance(raw_pois, list):
            raise AmapError(
                code="amap_response_invalid",
                message="高德 pois 字段应为列表。",
            )

        pois: list[Poi] = []

        for index, raw_poi in enumerate(raw_pois, start=1):
            try:
                pois.append(_parse_poi(raw_poi))
            except ValueError:
                # Pydantic ValidationError 也属于 ValueError。
                # 任意一条记录失败，整次查询明确报错。
                raise AmapError(
                    code="amap_poi_invalid",
                    message=(
                        f"第 {index} 条 POI 的字段或坐标不符合要求。"
                    ),
                ) from None

        return PoiSearchResult(
            city=query.city,
            keyword=query.keyword,
            pois=pois,
        )

    def resolve_district(
        self,
        query: DistrictQuery,
    ) -> DistrictResult:
        """把名称或 adcode 解析成一个明确的行政区。

        参数：
            query：
                已通过 DistrictQuery 校验的查询条件。

        返回值：
            DistrictResult：
                包含匹配记录、数据来源和查询时间。

        异常：
            AmapError：
                请求失败、字段不合格、匹配不明确，
                或行政级别不在当前支持范围内。
        """

        params: dict[str, str | int] = {
            "key": self._api_key,
            "keywords": query.keyword,
            "subdistrict": 0,
            "extensions": "base",
            "output": "JSON",
            "offset": DISTRICT_PAGE_SIZE,
            "page": 1,
        }

        if query.province_adcode is not None:
            params["filter"] = query.province_adcode

        payload = self._request_json(
            AMAP_DISTRICT_URL,
            params,
        )

        raw_districts = payload.get("districts")

        if not isinstance(raw_districts, list):
            raise AmapError(
                code="amap_response_invalid",
                message="高德 districts 字段应为列表。",
            )

        # 高德最外层单页最多返回 20 条。
        # 本步采用保守策略：满页时要求缩小范围，
        # 避免遗漏后续页中的同名候选。
        if len(raw_districts) >= DISTRICT_PAGE_SIZE:
            raise AmapError(
                code="district_query_too_broad",
                message=(
                    "候选达到单页上限，无法确认唯一结果；"
                    "请补充省级编码或明确的六位 adcode。"
                ),
            )

        districts: list[DistrictInfo] = []

        for index, raw_district in enumerate(
            raw_districts,
            start=1,
        ):
            try:
                districts.append(
                    _parse_district(raw_district)
                )
            except ValueError:
                raise AmapError(
                    code="amap_district_invalid",
                    message=(
                        f"第 {index} 条行政区记录的字段不符合要求。"
                    ),
                ) from None

        matches: list[DistrictInfo] = []

        for district in districts:
            exact_match = (
                query.keyword == district.name
                or query.keyword == district.adcode
            )

            # 只允许市级名称省略末尾的“市”。
            # 不随意删除“区”“县”，也不做包含匹配。
            city_alias_match = (
                district.level in {"city", "province"}
                and district.name.endswith("市")
                and query.keyword == district.name.removesuffix("市")
            )

            if exact_match or city_alias_match:
                matches.append(district)

        if not matches:
            raise AmapError(
                code="district_not_found",
                message=(
                    "没有找到符合匹配规则的行政区；"
                    "请使用完整名称或明确的六位 adcode。"
                ),
            )

        if len(matches) > 1:
            raise AmapError(
                code="district_ambiguous",
                message=(
                    "查询匹配到多个行政区；"
                    "请补充省级编码，或改用明确的六位 adcode。"
                ),
            )

        region = matches[0]

        # 对调用方指定的省级范围，再做一次基本一致性检查。
        # 这里只检查编码前两位，不推测或改写外部返回的编码。
        if (
            query.province_adcode is not None
            and region.adcode[:2] != query.province_adcode[:2]
        ):
            raise AmapError(
                code="amap_district_invalid",
                message="高德返回的行政区编码与指定省级范围不一致。",
            )

        supported_level = (
            region.level in {"city", "district"}
            or (
                region.level == "province"
                and region.name in MUNICIPALITY_NAMES
            )
        )

        if not supported_level:
            raise AmapError(
                code="district_level_unsupported",
                message=(
                    "当前只支持市、区县和直辖市；"
                    "请提供更明确的旅行目的地。"
                ),
            )

        return DistrictResult(
            keyword=query.keyword,
            province_adcode=query.province_adcode,
            region=region,
        )
    def get_current_weather(
        self,
        query: WeatherQuery,
    ) -> CurrentWeather:
        """查询指定 adcode 的实况天气。

        参数：
            query：
                已通过 WeatherQuery 校验的地区编码。

        返回值：
            CurrentWeather：
                包含天气字段、供应商发布时间和查询时间。

        异常：
            AmapError：
                请求失败、没有天气记录、数据不合格，
                或返回的地区编码与请求不一致。
        """

        params = {
            "key": self._api_key,
            "city": query.adcode,
            "extensions": "base",
            "output": "JSON",
        }

        # 沿用上一节的 HTTP、JSON 和高德业务状态检查。
        payload = self._request_json(
            AMAP_WEATHER_URL,
            params,
        )

        raw_lives = payload.get("lives")

        if not isinstance(raw_lives, list):
            raise AmapError(
                code="amap_response_invalid",
                message="高德 lives 字段应为列表。",
            )

        if not raw_lives:
            raise AmapError(
                code="weather_not_available",
                message="高德本次没有返回该地区的实况天气。",
            )

        # 当前接口按一个 adcode 查询一条实况记录。
        # 对意外的多个结果明确报错，避免任意选择。
        if len(raw_lives) != 1:
            raise AmapError(
                code="amap_weather_invalid",
                message="高德返回了数量不符合预期的实况天气记录。",
            )

        try:
            result = _parse_current_weather(
                raw_lives[0]
            )
        except (ValueError, OverflowError):
            # 包括数值转换、日期解析和 Pydantic 校验失败。
            # 不把包含原始数据的异常直接交给调用方。
            raise AmapError(
                code="amap_weather_invalid",
                message="高德实况天气字段或发布时间不符合要求。",
            ) from None

        if result.adcode != query.adcode:
            raise AmapError(
                code="amap_weather_region_mismatch",
                message="高德返回的天气地区编码与请求不一致。",
            )

        return result