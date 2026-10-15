"""测试行政区解析、歧义处理和返回数据校验。"""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.clients.amap import AmapClient, AmapError
from app.models.location import (
    DistrictQuery,
    DistrictResult,
)


Handler = Callable[[httpx.Request], httpx.Response]
ClientFactory = Callable[[Handler], AmapClient]


@pytest.fixture
def valid_payload() -> dict[str, Any]:
    """每个测试获得一份独立的模拟响应。"""
    return {
        "status": "1",
        "infocode": "10000",
        "districts": [
            {
                "name": " 北京市 ",
                "adcode": "110000",
                "level": "province",
                # 额外字段不会直接进入业务模型。
                "citycode": "010",
                "districts": [],
            }
        ],
    }


@pytest.fixture
def client_factory() -> Iterator[ClientFactory]:
    """创建本地模拟客户端，并在测试结束后统一关闭。"""

    clients: list[AmapClient] = []

    def create_client(handler: Handler) -> AmapClient:
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


@pytest.mark.parametrize(
    "keyword",
    ["北京", "北京市", "110000"],
)
def test_resolve_beijing(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    keyword: str,
) -> None:
    """简称、完整名称和 adcode 都能匹配同一条记录。"""

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=valid_payload)

    client = client_factory(handler)
    result = client.resolve_district(
        DistrictQuery(keyword=f" {keyword} ")
    )

    assert isinstance(result, DistrictResult)
    assert result.keyword == keyword
    assert result.region.name == "北京市"
    assert result.region.adcode == "110000"
    assert result.region.level == "province"
    assert result.source == "amap"
    assert result.queried_at.utcoffset() == timedelta(0)

    assert len(requests) == 1

    request = requests[0]
    params = request.url.params

    assert request.method == "GET"
    assert request.url.host == "restapi.amap.com"
    assert request.url.path == "/v3/config/district"
    assert params["keywords"] == keyword
    assert params["subdistrict"] == "0"
    assert params["extensions"] == "base"
    assert params["offset"] == "20"
    assert params["page"] == "1"
    assert "filter" not in params


def test_filters_by_province(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """省级范围应作为 filter 发送，同时允许解析区县。"""

    valid_payload["districts"] = [
        {
            "name": "海淀区",
            "adcode": "110108",
            "level": "district",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["filter"] == "110000"
        return httpx.Response(200, json=valid_payload)

    client = client_factory(handler)
    result = client.resolve_district(
        DistrictQuery(
            keyword="海淀区",
            province_adcode="110000",
        )
    )

    assert result.region.adcode == "110108"
    assert result.region.level == "district"
    assert result.province_adcode == "110000"


def test_resolves_city_alias(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """普通市级记录也允许省略名称末尾的“市”."""

    valid_payload["districts"] = [
        {
            "name": "测试市",
            "adcode": "990100",
            "level": "city",
        }
    ]

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    result = client.resolve_district(
        DistrictQuery(keyword="测试")
    )

    assert result.region.name == "测试市"
    assert result.region.level == "city"


def test_empty_result_is_not_found(
    client_factory: ClientFactory,
) -> None:
    """查不到记录时不生成或猜测编码。"""

    client = client_factory(
        lambda request: httpx.Response(
            200,
            json={"status": "1", "districts": []},
        )
    )

    with pytest.raises(AmapError) as caught:
        client.resolve_district(
            DistrictQuery(keyword="测试市")
        )

    assert caught.value.code == "district_not_found"


def test_same_name_is_ambiguous(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """两个同名候选不能直接取第一条。"""

    valid_payload["districts"] = [
        {
            "name": "测试区",
            "adcode": "110123",
            "level": "district",
        },
        {
            "name": "测试区",
            "adcode": "220123",
            "level": "district",
        },
    ]

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.resolve_district(
            DistrictQuery(keyword="测试区")
        )

    assert caught.value.code == "district_ambiguous"


def test_partial_name_is_not_matched(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """输入“北”不能通过包含匹配被认定为“北京市”."""

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.resolve_district(
            DistrictQuery(keyword="北")
        )

    assert caught.value.code == "district_not_found"


@pytest.mark.parametrize(
    "name, adcode, level",
    [
        ("中国", "100000", "country"),
        ("测试省", "990000", "province"),
        ("测试街道", "110108", "street"),
    ],
)
def test_unsupported_level_is_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    name: str,
    adcode: str,
    level: str,
) -> None:
    """国家、普通省份和街道不作为当前旅行目的地结果。"""

    valid_payload["districts"] = [
        {
            "name": name,
            "adcode": adcode,
            "level": level,
        }
    ]

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.resolve_district(
            DistrictQuery(keyword=name)
        )

    assert caught.value.code == "district_level_unsupported"


@pytest.mark.parametrize(
    "changes",
    [
        {"adcode": 110000},
        {"adcode": "11000"},
        {"level": "town"},
        {"name": None},
        {"name": "   "},
    ],
)
def test_bad_district_fields_are_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
    changes: dict[str, object],
) -> None:
    """整数编码、错误长度、未知级别和无效名称应明确报错。"""

    valid_payload["districts"][0].update(changes)

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.resolve_district(
            DistrictQuery(keyword="北京")
        )

    assert caught.value.code == "amap_district_invalid"


def test_bad_record_is_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """列表中的每条行政区记录必须是对象。"""

    valid_payload["districts"] = [None]

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.resolve_district(
            DistrictQuery(keyword="北京")
        )

    assert caught.value.code == "amap_district_invalid"


def test_bad_container_is_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """districts 必须是列表。"""

    valid_payload["districts"] = {}

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.resolve_district(
            DistrictQuery(keyword="北京")
        )

    assert caught.value.code == "amap_response_invalid"


def test_full_first_page_cannot_confirm_unique_result(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """第一页满 20 条时，不把本页匹配当作完整查询的唯一结果。"""

    for index in range(1, 20):
        valid_payload["districts"].append(
            {
                "name": f"测试市{index}",
                "adcode": f"9901{index:02d}",
                "level": "city",
            }
        )

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.resolve_district(
            DistrictQuery(keyword="北京")
        )

    assert caught.value.code == "district_query_too_broad"


def test_filter_mismatch_is_rejected(
    client_factory: ClientFactory,
    valid_payload: dict[str, Any],
) -> None:
    """模拟上游返回了不属于指定省级范围的编码。"""

    client = client_factory(
        lambda request: httpx.Response(200, json=valid_payload)
    )

    with pytest.raises(AmapError) as caught:
        client.resolve_district(
            DistrictQuery(
                keyword="北京",
                province_adcode="310000",
            )
        )

    assert caught.value.code == "amap_district_invalid"


@pytest.mark.parametrize(
    "data",
    [
        {"keyword": ""},
        {"keyword": "   "},
        {
            "keyword": "北京",
            "province_adcode": "110108",
        },
        {
            "keyword": "北京",
            "province_adcode": 110000,
        },
    ],
)
def test_invalid_query_is_rejected(
    data: dict[str, Any],
) -> None:
    """查询条件不合格时，在模型构造阶段拒绝。"""

    with pytest.raises(ValidationError):
        DistrictQuery(**data)
