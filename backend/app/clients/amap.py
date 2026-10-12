"""调用高德 POI 搜索，并转换为项目业务模型。"""

import httpx
from pydantic import SecretStr

from app.models.poi import (
    Poi,
    PoiSearchQuery,
    PoiSearchResult,
)


AMAP_SEARCH_URL = "https://restapi.amap.com/v3/place/text"


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
    # float() 负责显式转换字符串。
    # 无法解析时抛出 ValueError。
    longitude = float(parts[0].strip())
    latitude = float(parts[1].strip())

    raw_address = raw.get("address")

    # 对已知的缺失形式进行明确转换。
    if raw_address is None or raw_address == []:
        address = None
    elif isinstance(raw_address, str):
        address = raw_address.strip() or None
    else:
        raise ValueError("地址类型不符合预期。")

    # 这里只挑选项目需要的字段。
    # 高德额外返回的其他字段不会直接进入业务模型。
    #
    # Poi 继续校验：
    # 必填字段、字符串长度、坐标范围和数值有限性。
    return Poi(
        poi_id=raw.get("id"),
        name=raw.get("name"),
        address=address,
        longitude=longitude,
        latitude=latitude,
    )


class AmapClient:
    """管理高德 HTTP 调用和返回数据转换。"""

    def __init__(
        self,
        api_key: SecretStr | None,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """创建客户端，但暂不发送高德请求。

        参数：
            api_key:
                高德 Web 服务 Key，通常来自 Settings。

            timeout_seconds:
                传给 HTTPX 的超时参数。

            transport:
                正常调用时使用默认传输。
                测试时可以注入 MockTransport。
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

    def search_pois(
        self,
        query: PoiSearchQuery,
    ) -> PoiSearchResult:
        """搜索候选地点，返回经过校验的业务结果。

        参数：
            query:
                已经通过 PoiSearchQuery 校验的搜索条件。

        返回值：
            PoiSearchResult:
                包含来源、查询时间和规范化 POI 列表。

        异常：
            AmapError:
                请求失败、业务失败或返回数据不合格。
        """

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

        try:
            response = self._http_client.get(
                AMAP_SEARCH_URL,
                params=params,
            )
            response.raise_for_status()

        except httpx.TimeoutException:
            raise AmapError(
                code="amap_timeout",
                message="高德请求超时，请稍后重试。",
            ) from None

        except httpx.HTTPStatusError as exc:
            # 不使用完整 HTTP 异常文本，
            # 避免把包含 Key 的请求 URL 带到调用方。
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
                # Pydantic 的 ValidationError 也属于 ValueError。
                # 这里统一转换为客户端自己的异常。
                #
                # 任意一条记录失败，本次查询都明确报错。
                # 不返回已经解析的部分结果。
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