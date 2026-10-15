"""测试高德客户端的数据转换、异常处理和空结果。"""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.clients.amap import AmapClient, AmapError
from app.models.location import (
    PoiSearchQuery,
    PoiSearchResult,
)


# 给函数类型起一个名称，简化下面的类型注解。
Handler = Callable[[httpx.Request], httpx.Response]
ClientFactory = Callable[[Handler], AmapClient]


@pytest.fixture
def query() -> PoiSearchQuery:
    """提供经过校验的查询条件。"""

    return PoiSearchQuery(
        city=" 北京 ",
        keyword=" 测试景点 ",
    )


@pytest.fixture
def valid_payload() -> dict[str, Any]:
    """提供一份新的高德格式模拟响应。"""

    return {
        "status": "1",
        "infocode": "10000",
        "count": "1",
        "pois": [
            {
                "id": "test-poi-001",
                "name": " 测试景点 ",
                "address": " 测试街 1 号 ",
                "location": "116.4,39.9",
                # 外部服务的额外字段不直接进入业务模型。
                "type": "测试类型",
            }
        ],
    }


@pytest.fixture
def client_factory() -> Iterator[ClientFactory]:
    """创建使用本地响应的客户端，并统一负责关闭。"""

    clients: list[AmapClient] = []

    def create_client(handler: Handler) -> AmapClient:
        """根据响应处理函数创建一个测试客户端。"""

        client = AmapClient(
            api_key=SecretStr("test-key"),
            transport=httpx.MockTransport(handler),
        )

        clients.append(client)
        return client

    try:
        yield create_client
    finally:
        for client in clients:
            client.close()


def test_search_returns_normalized_poi(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
    valid_payload: dict[str, Any],
) -> None:
    """合法响应应转换成业务对象，并发送正确的查询参数。"""

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=valid_payload)

    client = client_factory(handler)
    result = client.search_pois(query)

    assert isinstance(result, PoiSearchResult)
    assert result.city == "北京"
    assert result.keyword == "测试景点"
    assert result.source == "amap"
    assert result.coordinate_system == "GCJ-02"
    assert result.queried_at.utcoffset() == timedelta(0)

    assert len(result.pois) == 1

    poi = result.pois[0]

    assert poi.poi_id == "test-poi-001"
    assert poi.name == "测试景点"
    assert poi.address == "测试街 1 号"
    assert poi.longitude == pytest.approx(116.4)
    assert poi.latitude == pytest.approx(39.9)

    assert len(requests) == 1

    request = requests[0]
    params = request.url.params

    assert request.method == "GET"
    assert request.url.host == "restapi.amap.com"
    assert request.url.path == "/v3/place/text"
    assert params["city"] == "北京"
    assert params["keywords"] == "测试景点"
    assert params["citylimit"] == "true"
    assert params["offset"] == "5"


@pytest.mark.parametrize("address", [None, [], "", "   "])
def test_missing_address_becomes_none(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
    valid_payload: dict[str, Any],
    address: object,
) -> None:
    """已知的缺失地址形式应转换为 None。"""

    valid_payload["pois"][0]["address"] = address

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    result = client.search_pois(query)

    assert result.pois[0].address is None
    assert result.pois[0].longitude == pytest.approx(116.4)


@pytest.mark.parametrize(
    "bad_location",
    [
        "116.4",
        "abc,39.9",
        "181,39.9",
        "116.4,91",
        "nan,39.9",
        "116.4,inf",
        None,
        [],
    ],
)
def test_invalid_coordinate_rejects_entire_result(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
    valid_payload: dict[str, Any],
    bad_location: object,
) -> None:
    """第一条合法、第二条非法时，应明确拒绝整次结果。"""

    bad_poi = valid_payload["pois"][0].copy()
    bad_poi["id"] = "test-poi-002"
    bad_poi["location"] = bad_location

    valid_payload["pois"].append(bad_poi)

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.search_pois(query)

    assert caught.value.code == "amap_poi_invalid"
    assert "第 2 条" in str(caught.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": None},
        {"name": "   "},
    ],
)
def test_required_poi_fields_are_validated(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
    valid_payload: dict[str, Any],
    changes: dict[str, object],
) -> None:
    """POI 标识和名称不合格时应拒绝结果。"""

    valid_payload["pois"][0].update(changes)

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.search_pois(query)

    assert caught.value.code == "amap_poi_invalid"


def test_unexpected_address_type_is_rejected(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
    valid_payload: dict[str, Any],
) -> None:
    """非空地址数组不能被悄悄当成地址缺失。"""

    valid_payload["pois"][0]["address"] = ["异常地址形式"]

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.search_pois(query)

    assert caught.value.code == "amap_poi_invalid"


def test_business_failure_is_reported(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
) -> None:
    """HTTP 200 下的高德业务失败仍应抛出异常。"""

    payload = {
        "status": "0",
        "infocode": "10001",
        "info": "INVALID_USER_KEY",
    }

    client = client_factory(
        lambda request: httpx.Response(200, json=payload)
    )

    with pytest.raises(AmapError) as caught:
        client.search_pois(query)

    assert caught.value.code == "amap_business_error"
    assert caught.value.provider_code == "10001"


def test_http_failure_is_reported(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
) -> None:
    """HTTP 非成功状态应映射为客户端错误。"""

    client = client_factory(
        lambda request: httpx.Response(
            503,
            json={"message": "模拟上游失败"},
        )
    )

    with pytest.raises(AmapError) as caught:
        client.search_pois(query)

    assert caught.value.code == "amap_http_error"
    assert "503" in str(caught.value)
    assert "test-key" not in str(caught.value)


@pytest.mark.parametrize(
    "exception_type, expected_code",
    [
        (httpx.ReadTimeout, "amap_timeout"),
        (httpx.ConnectError, "amap_connection_error"),
    ],
)
def test_transport_errors_are_mapped(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
    exception_type: type[httpx.RequestError],
    expected_code: str,
) -> None:
    """超时和连接错误应转换为固定的业务异常。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise exception_type(
            "原始模拟异常文本",
            request=request,
        )

    client = client_factory(handler)

    with pytest.raises(AmapError) as caught:
        client.search_pois(query)

    assert caught.value.code == expected_code
    assert "原始模拟异常文本" not in str(caught.value)


def test_invalid_json_is_rejected(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
) -> None:
    """无法解析的 JSON 应返回明确错误。"""

    client = client_factory(
        lambda request: httpx.Response(200, text="{")
    )

    with pytest.raises(AmapError) as caught:
        client.search_pois(query)

    assert caught.value.code == "amap_response_invalid"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"status": "unexpected", "pois": []},
        {"status": "1", "pois": {}},
    ],
)
def test_invalid_response_structure_is_rejected(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
    payload: object,
) -> None:
    """错误的最外层、业务状态或列表结构应被拒绝。"""

    client = client_factory(
        lambda request: httpx.Response(200, json=payload)
    )

    with pytest.raises(AmapError) as caught:
        client.search_pois(query)

    assert caught.value.code == "amap_response_invalid"


def test_empty_search_result_is_valid(
    client_factory: ClientFactory,
    query: PoiSearchQuery,
) -> None:
    """没有匹配记录是合法结果，不应编造地点。"""

    payload = {
        "status": "1",
        "infocode": "10000",
        "pois": [],
    }

    client = client_factory(
        lambda request: httpx.Response(200, json=payload)
    )

    result = client.search_pois(query)

    assert result.pois == []
    assert result.source == "amap"


@pytest.mark.parametrize("api_key", [None, SecretStr("")])
def test_missing_key_is_rejected(
    api_key: SecretStr | None,
) -> None:
    """缺少 Key 时，应在发送请求之前拒绝初始化。"""

    with pytest.raises(AmapError) as caught:
        AmapClient(api_key=api_key)

    assert caught.value.code == "amap_not_configured"
