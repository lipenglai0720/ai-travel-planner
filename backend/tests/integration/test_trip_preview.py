"""旅行预览接口测试：验证响应、输入校验和业务调用次数。"""

from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.routes.trips import get_trip_service
from app.main import app
from app.models.trip import (
    TripPreview,
    TripRequest,
)
from app.services.trip_service import TripService


class CountingTripService(TripService):
    """测试用服务：记录 preview 调用次数，并执行原有业务逻辑。"""

    def __init__(self) -> None:
        """初始化父类及本次测试的调用计数。"""

        super().__init__()
        self.preview_call_count = 0

    def preview(self, request: TripRequest) -> TripPreview:
        """记录一次调用，再交给父类生成真实摘要。"""

        self.preview_call_count += 1

        # super() 用于调用父类实现。
        # 正常请求仍然执行项目已有的预览业务逻辑。
        return super().preview(request)


@pytest.fixture
def valid_payload() -> dict[str, object]:
    """为每个测试案例提供一份新的合法输入字典。"""

    return {
        "destination": " 北京 ",
        "start_date": "2026-11-01",
        "end_date": "2026-11-03",
        "travelers": 2,
        "budget_cents": 600000,
        "transportation": "public_transit",
        "accommodation_preference": "economy",
        "room_count": 1,
        "preferences": ["历史文化", "美食"],
        "pace": "relaxed",
    }


@pytest.fixture
def spy_service() -> CountingTripService:
    """为每个测试案例创建新的计数服务。"""

    return CountingTripService()


@pytest.fixture
def client(
    spy_service: CountingTripService,
) -> Iterator[TestClient]:
    """提供测试客户端，并在测试结束后恢复依赖映射。"""

    def override_trip_service() -> TripService:
        """让当前测试请求使用同一个计数服务对象。"""

        return spy_service

    # 保存原有映射，以便测试结束后恢复。
    original_overrides = app.dependency_overrides.copy()

    # 字典的键是路由实际使用的原依赖函数。
    app.dependency_overrides[get_trip_service] = override_trip_service

    try:
        # 上下文管理器负责测试客户端的打开和关闭。
        with TestClient(app) as test_client:
            # 暂停 fixture，将客户端交给当前测试函数。
            yield test_client
    finally:
        # 即使测试失败，也恢复依赖映射。
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


@pytest.mark.parametrize(
    "date_changes, expected_days",
    [
        pytest.param(
            {},
            3,
            id="three-days",
        ),
        pytest.param(
            {"end_date": "2026-11-01"},
            1,
            id="same-day",
        ),
        pytest.param(
            {"end_date": "2026-11-07"},
            7,
            id="seven-days",
        ),
    ],
)
def test_preview_success(
    client: TestClient,
    spy_service: CountingTripService,
    valid_payload: dict[str, object],
    date_changes: dict[str, object],
    expected_days: int,
) -> None:
    """合法请求返回正确摘要，并且只调用一次预览业务方法。"""

    payload = valid_payload.copy()
    payload.update(date_changes)

    # json= 将 Python 字典编码为 JSON 请求体，
    # 并设置相应的 Content-Type。
    response = client.post(
        "/api/v1/trips/preview",
        json=payload,
    )

    assert response.status_code == 200, response.text

    body = response.json()

    # 按接口契约检查摘要。
    # 总预算仍然是 600000 分，不因人数为 2 而再次乘以 2。
    assert body["data"] == {
        "destination": "北京",
        "start_date": payload["start_date"],
        "end_date": payload["end_date"],
        "day_count": expected_days,
        "travelers": 2,
        "room_count": 1,
        "requested_budget_cents": 600000,
        "currency": "CNY",
    }

    assert body["meta"]["warnings"] == []

    # 请求标识每次变化，因此检查它是合法的规范 UUID 字符串。
    request_id = body["meta"]["request_id"]
    assert str(UUID(request_id)) == request_id

    # 正常测试也检查计数，确认依赖替换确实生效。
    assert spy_service.preview_call_count == 1


@pytest.mark.parametrize(
    "changes, expected_field, expected_reason",
    [
        pytest.param(
            {"travelers": 0},
            "travelers",
            "value_too_small",
            id="zero-travelers",
        ),
        pytest.param(
            {"travelers": True},
            "travelers",
            "integer_required",
            id="boolean-travelers",
        ),
        pytest.param(
            {"budget_cents": 600000.0},
            "budget_cents",
            "integer_required",
            id="float-budget",
        ),
        pytest.param(
            {"end_date": "2026-10-31"},
            "end_date",
            "date_order_invalid",
            id="reversed-dates",
        ),
        pytest.param(
            {"end_date": "2026-11-08"},
            "end_date",
            "trip_too_long",
            id="too-many-days",
        ),
        pytest.param(
            {"room_count": 3},
            "room_count",
            "room_count_exceeds_travelers",
            id="too-many-rooms",
        ),
        pytest.param(
            {"days": 3},
            "days",
            "unexpected_field",
            id="unexpected-field",
        ),
    ],
)
def test_preview_rejects_invalid_input(
    client: TestClient,
    spy_service: CountingTripService,
    valid_payload: dict[str, object],
    changes: dict[str, object],
    expected_field: str,
    expected_reason: str,
) -> None:
    """非法输入应返回统一错误响应，且不执行预览业务。"""

    payload = valid_payload.copy()
    payload.update(changes)

    response = client.post(
        "/api/v1/trips/preview",
        json=payload,
    )

    assert response.status_code == 422, response.text

    body = response.json()

    # 验证最外层结构，防止继续返回旧的 detail 格式。
    assert set(body) == {"error", "meta"}

    # 精确验证错误契约。
    # 这里也确保错误信息没有夹带原始输入值等额外字段。
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

    assert body["meta"]["warnings"] == []

    # 错误响应也应包含合法的 UUID 标识。
    request_id = body["meta"]["request_id"]
    assert str(UUID(request_id)) == request_id

    # 输入不合法时，真正的 preview() 业务方法不应执行。
    assert spy_service.preview_call_count == 0

def test_preview_reports_multiple_field_errors(
    client: TestClient,
    spy_service: CountingTripService,
    valid_payload: dict[str, object],
) -> None:
    """多个字段同时非法时，应返回全部字段错误。"""

    payload = valid_payload.copy()
    payload.update(
        {
            "travelers": 0,
            "budget_cents": 0,
        }
    )

    response = client.post(
        "/api/v1/trips/preview",
        json=payload,
    )

    assert response.status_code == 422, response.text

    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"

    details = body["error"]["details"]
    assert len(details) == 2

    # 使用集合比较，不要求错误列表必须按某个顺序排列。
    actual_errors = {
        (item["field"], item["reason"])
        for item in details
    }

    assert actual_errors == {
        ("travelers", "value_too_small"),
        ("budget_cents", "value_too_small"),
    }

    assert spy_service.preview_call_count == 0


def test_preview_rejects_invalid_json(
    client: TestClient,
    spy_service: CountingTripService,
) -> None:
    """JSON 语法错误也应返回统一的请求校验错误结构。"""

    # 故意发送不完整的 JSON 文本。
    # 使用 content 直接发送文本，才能保留这个语法错误。
    response = client.post(
        "/api/v1/trips/preview",
        content='{"destination":',
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 422, response.text

    body = response.json()

    assert body["error"] == {
        "code": "VALIDATION_ERROR",
        "message": "请求参数校验失败",
        "details": [
            {
                "field": "body",
                "reason": "invalid_json",
            }
        ],
    }

    assert spy_service.preview_call_count == 0
