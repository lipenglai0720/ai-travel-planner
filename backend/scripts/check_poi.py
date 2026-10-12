"""验证可复用高德客户端及 POI 数据转换。"""

import argparse

import httpx
from pydantic import SecretStr, ValidationError

from app.clients.amap import AmapClient, AmapError
from app.core.config import Settings
from app.models.poi import PoiSearchQuery


def invalid_location_response(
    request: httpx.Request,
) -> httpx.Response:
    """返回含有坏坐标的本地模拟响应。"""

    return httpx.Response(
        status_code=200,
        json={
            "status": "1",
            "infocode": "10000",
            "pois": [
                {
                    "id": "test-poi-001",
                    "name": "测试景点",
                    "address": [],
                    "location": "bad-coordinate",
                }
            ],
        },
    )


def print_amap_error(exc: AmapError) -> None:
    """只打印客户端提供的错误标识和整理后的说明。"""

    print(f"[失败] {exc.code}：{exc}")

    if exc.provider_code is not None:
        print(f"高德错误码：{exc.provider_code}")


def main() -> int:
    """执行一次查询，并返回进程退出码。"""

    parser = argparse.ArgumentParser(
        description="验证 AmapClient 和规范化 POI 数据。",
    )

    parser.add_argument("--city", default="北京")
    parser.add_argument("--keyword", default="故宫博物院")

    parser.add_argument(
        "--mock-invalid-location",
        action="store_true",
        help="在本地模拟坏坐标，不发送真实高德请求。",
    )

    args = parser.parse_args()

    try:
        query = PoiSearchQuery(
            city=args.city,
            keyword=args.keyword,
        )

        if args.mock_invalid_location:
            print("[模拟] 使用本地坏坐标响应。")

            api_key = SecretStr("offline-test-key")
            timeout_seconds = 10.0
            transport = httpx.MockTransport(
                invalid_location_response
            )
        else:
            settings = Settings()

            api_key = settings.amap_web_api_key
            timeout_seconds = settings.amap_timeout_seconds
            transport = None

    except ValidationError as exc:
        print("[失败] input_or_config_invalid：输入或配置不合法。")

        for error in exc.errors(
            include_input=False,
            include_context=False,
        ):
            field = ".".join(
                str(part) for part in error["loc"]
            )
            print(f"  {field}: {error['type']}")

        return 2

    try:
        client = AmapClient(
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
    except AmapError as exc:
        print_amap_error(exc)
        return 2

    try:
        result = client.search_pois(query)
    except AmapError as exc:
        print_amap_error(exc)
        return 1
    finally:
        # 成功、网络失败或数据校验失败时都关闭客户端。
        client.close()

    print(
        "[通过] POI 查询和数据校验完成，"
        f"本页返回 {len(result.pois)} 条记录。"
    )

    print(result.model_dump_json(indent=2))

    if not result.pois:
        print("[提示] 没有匹配结果，请检查城市和关键词。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())