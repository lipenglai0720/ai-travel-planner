"""测试 POI 查询接口、异常映射和客户端生命周期。"""

from collections.abc import Iterator
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.routes.pois import get_poi_service
from app.clients.amap import AmapClient, AmapError
from app.main import app
from app.models.location import (
    Poi,
    PoiSearchQuery,
    PoiSearchResult,
)
from app.services import poi_service as poi_service_module
from app.services.poi_service import PoiService


@pytest.fixture
def mock_service() -> Mock:
    """提供返回合法业务结果的地点查询服务替身。"""

    service = Mock(spec=PoiService)

    service.search.return_value = PoiSearchResult(
        city="北京",
        keyword="测试景点",
        pois=[
            Poi(
                poi_id="test-poi-001",
                name="测试景点",
                address="测试地址",
                longitude=116.4,
                latitude=39.9,
            )
        ],
    )

    return service


@pytest.fixture
def client(
    mock_service: Mock,
) -> Iterator[TestClient]:
    """替换服务依赖，并在测试结束后恢复。"""

    def override_poi_service() -> PoiService:
        return mock_service

    original_overrides = app.dependency_overrides.copy()

    app.dependency_overrides[
        get_poi_service
    ] = override_poi_service

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def test_search_success(
    client: TestClient,
    mock_service: Mock,
) -> None:
    """合法参数返回统一成功响应，并执行一次服务调用。"""

    response = client.get(
        "/api/v1/pois/search",
        params={
            "city": " 北京 ",
            "keyword": " 测试景点 ",
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert set(body) == {"data", "meta"}
    assert body["data"] == (
        mock_service.search.return_value
        .model_dump(mode="json")
    )

    assert body["meta"]["warnings"]
    assert "候选" in body["meta"]["warnings"][0]

    request_id = body["meta"]["request_id"]
    assert str(UUID(request_id)) == request_id

    mock_service.search.assert_called_once()

    actual_query = mock_service.search.call_args.args[0]

    assert isinstance(actual_query, PoiSearchQuery)
    assert actual_query.city == "北京"
    assert actual_query.keyword == "测试景点"


def test_empty_result_returns_200(
    client: TestClient,
    mock_service: Mock,
) -> None:
    """合法空结果返回 200，并提供调整查询条件的提醒。"""

    mock_service.search.return_value = PoiSearchResult(
        city="北京",
        keyword="测试景点",
        pois=[],
    )

    response = client.get(
        "/api/v1/pois/search",
        params={
            "city": "北京",
            "keyword": "测试景点",
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert body["data"]["pois"] == []
    assert any(
        "未找到" in warning
        for warning in body["meta"]["warnings"]
    )

    mock_service.search.assert_called_once()


@pytest.mark.parametrize(
    "params, expected_field, expected_reason",
    [
        (
            {"city": "北京"},
            "keyword",
            "required",
        ),
        (
            {"city": "", "keyword": "测试景点"},
            "city",
            "text_too_short",
        ),
        (
            {"city": "北京", "keyword": "   "},
            "keyword",
            "text_too_short",
        ),
        (
            {"city": "北京", "keyword": "测" * 81},
            "keyword",
            "text_too_long",
        ),
        (
            {
                "city": "北京",
                "keyword": "测试景点",
                "page": "1",
            },
            "page",
            "unexpected_field",
        ),
    ],
)
def test_invalid_query_is_rejected(
    client: TestClient,
    mock_service: Mock,
    params: dict[str, str],
    expected_field: str,
    expected_reason: str,
) -> None:
    """非法查询参数返回统一 422，并阻止业务调用。"""

    response = client.get(
        "/api/v1/pois/search",
        params=params,
    )

    assert response.status_code == 422, response.text

    body = response.json()

    assert set(body) == {"error", "meta"}
    assert body["error"] == {
        "code": "VALIDATION_ERROR",
        "message": "请求参数校验失败",
        "details": [
            {
                "field": expected_field,
                "reason": expected_reason,
            }
        ],
    }

    mock_service.search.assert_not_called()


@pytest.mark.parametrize(
    "error_code, expected_status",
    [
        ("amap_not_configured", 503),
        ("amap_configuration_invalid", 503),
        ("amap_timeout", 504),
        ("amap_connection_error", 502),
        ("amap_http_error", 502),
        ("amap_business_error", 502),
        ("amap_response_invalid", 502),
        ("amap_poi_invalid", 502),
    ],
)
def test_amap_errors_are_mapped(
    client: TestClient,
    mock_service: Mock,
    error_code: str,
    expected_status: int,
) -> None:
    """客户端错误应转换成约定的 HTTP 状态与错误结构。"""

    internal_message = "内部模拟异常文本，不应进入 HTTP 响应。"

    mock_service.search.side_effect = AmapError(
        code=error_code,
        message=internal_message,
    )

    response = client.get(
        "/api/v1/pois/search",
        params={
            "city": "北京",
            "keyword": "测试景点",
        },
    )

    assert response.status_code == expected_status, response.text

    body = response.json()

    assert set(body) == {"error", "meta"}
    assert body["error"]["code"] == error_code
    assert body["error"]["details"] == []

    request_id = body["meta"]["request_id"]
    assert str(UUID(request_id)) == request_id

    assert internal_message not in response.text

    mock_service.search.assert_called_once()


@pytest.mark.parametrize(
    "query_fails",
    [False, True],
    ids=["success", "failure"],
)
def test_service_closes_amap_client(
    client: TestClient,
    mock_service: Mock,
    monkeypatch: pytest.MonkeyPatch,
    query_fails: bool,
) -> None:
    """执行真实服务，检查成功和失败时都关闭客户端。"""

    amap_client = Mock(spec=AmapClient)

    amap_client.search_pois.return_value = (
        mock_service.search.return_value
    )

    if query_fails:
        amap_client.search_pois.side_effect = AmapError(
            code="amap_timeout",
            message="测试用超时。",
        )

    constructor = Mock(return_value=amap_client)

    # 替换服务模块实际使用的客户端构造器。
    monkeypatch.setattr(
        poi_service_module,
        "AmapClient",
        constructor,
    )

    real_service = PoiService(api_key=None)

    app.dependency_overrides[
        get_poi_service
    ] = lambda: real_service

    response = client.get(
        "/api/v1/pois/search",
        params={
            "city": "北京",
            "keyword": "测试景点",
        },
    )

    expected_status = 504 if query_fails else 200

    assert response.status_code == expected_status, response.text

    constructor.assert_called_once()
    amap_client.search_pois.assert_called_once()
    amap_client.close.assert_called_once_with()


def test_invalid_query_does_not_create_amap_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """即使没有配置 Key，非法输入也应先返回 422。"""

    constructor = Mock()

    monkeypatch.setattr(
        poi_service_module,
        "AmapClient",
        constructor,
    )

    real_service = PoiService(api_key=None)

    app.dependency_overrides[
        get_poi_service
    ] = lambda: real_service

    response = client.get(
        "/api/v1/pois/search",
        params={"city": "北京"},
    )

    assert response.status_code == 422, response.text

    # 输入校验失败，服务的 search() 不会执行，
    # 因而不会创建高德客户端。
    constructor.assert_not_called()
