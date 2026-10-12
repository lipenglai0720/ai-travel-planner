"""验证高德关键字搜索，并观察真实 POI 返回字段。"""

import argparse
import json
from datetime import datetime, timezone

import httpx
from pydantic import ValidationError

from app.core.config import Settings


# 固定使用高德官方的 HTTPS 关键字搜索地址。
# Key 通过请求参数传入，不写进这段地址常量。
AMAP_SEARCH_URL = "https://restapi.amap.com/v3/place/text"


def create_mock_error_transport() -> httpx.MockTransport:
    """创建本地模拟传输器：HTTP 成功，但高德业务失败。"""

    def handle_request(request: httpx.Request) -> httpx.Response:
        """返回模拟响应，不向真实高德服务发送请求。"""

        return httpx.Response(
            status_code=200,
            json={
                "status": "0",
                "info": "INVALID_USER_KEY",
                "infocode": "10001",
                "pois": [],
            },
        )

    # MockTransport 会把 HTTP 请求交给上面的本地函数处理。
    return httpx.MockTransport(handle_request)


def main() -> int:
    """执行一次查询，返回供命令行使用的进程退出码。"""

    parser = argparse.ArgumentParser(
        description="验证高德 Web 服务 Key 和 POI 关键字搜索。",
    )

    parser.add_argument(
        "--city",
        default="北京",
        help="查询城市名称、citycode 或 adcode，默认：北京。",
    )

    parser.add_argument(
        "--keyword",
        default="故宫博物院",
        help="一个地点查询关键词，默认：故宫博物院。",
    )

    parser.add_argument(
        "--mock-error",
        action="store_true",
        help="使用本地模拟响应，验证 HTTP 200 下的业务失败处理。",
    )

    args = parser.parse_args()

    city = args.city.strip()
    keyword = args.keyword.strip()

    # 空城市、空关键词在本地直接拒绝。
    if not city or not keyword:
        print("[失败] invalid_input：城市和关键词不能为空。")
        return 2

    transport: httpx.BaseTransport | None = None

    if args.mock_error:
        # 这是明确标记的离线模拟值。
        # 请求会由 MockTransport 接管，不会发送到真实高德服务。
        api_key = "offline-test-key"
        timeout_seconds = 10.0
        transport = create_mock_error_transport()

        print("[模拟] 使用本地响应，未发送真实高德请求。")

    else:
        try:
            settings = Settings()
        except ValidationError as exc:
            print("[失败] config_invalid：请检查 backend/.env。")

            # 只显示配置字段和错误类型。
            # 不打印原始配置值或完整异常文本。
            for error in exc.errors(
                include_input=False,
                include_context=False,
            ):
                field = ".".join(
                    str(part) for part in error["loc"]
                )
                print(f"  {field}: {error['type']}")

            return 2

        secret_key = settings.amap_web_api_key

        api_key = (
            secret_key.get_secret_value().strip()
            if secret_key is not None
            else ""
        )

        if not api_key:
            print(
                "[失败] amap_not_configured："
                "请在 backend/.env 中填写 AMAP_WEB_API_KEY。"
            )
            return 2

        timeout_seconds = settings.amap_timeout_seconds

    params = {
        "key": api_key,
        "keywords": keyword,
        "city": city,
        "citylimit": "true",
        "offset": 5,
        "page": 1,
        "extensions": "base",
        "output": "JSON",
    }

    try:
        # with 负责管理客户端生命周期。
        # 正常结束或发生异常时，都会退出上下文并关闭客户端。
        with httpx.Client(
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
        ) as client:
            response = client.get(
                AMAP_SEARCH_URL,
                params=params,
            )

            print(f"[HTTP] {response.status_code}")

            # 第一层检查：HTTP 响应状态。
            # 非成功状态会抛出 HTTPStatusError。
            response.raise_for_status()

    # 超时也是请求异常的一种，因此先单独处理。
    except httpx.TimeoutException:
        print("[失败] amap_timeout：高德请求超时，请稍后重试。")
        return 1

    except httpx.HTTPStatusError as exc:
        # 只打印 HTTP 状态码。
        # 完整异常文本可能包含带有 Key 的请求 URL。
        print(
            "[失败] amap_http_error："
            f"HTTP {exc.response.status_code}。"
        )
        return 1

    except httpx.RequestError:
        print(
            "[失败] amap_connection_error："
            "请求未能完成，请检查网络和代理配置。"
        )
        return 1

    except ValueError:
        print(
            "[失败] http_client_configuration_invalid："
            "请检查 HTTP 客户端及代理配置。"
        )
        return 2

    try:
        payload = response.json()
    except ValueError:
        print(
            "[失败] amap_response_invalid："
            "返回内容不是有效 JSON。"
        )
        return 1

    if not isinstance(payload, dict):
        print(
            "[失败] amap_response_invalid："
            "响应最外层应为 JSON 对象。"
        )
        return 1

    # 第二层检查：高德业务状态。
    # 对本步使用的关键字搜索接口，status="1" 表示成功。
    status = payload.get("status")

    if status == "0":
        provider_code = payload.get("infocode")

        # 只打印符合预期格式的错误码，不打印完整上游响应。
        if not (
            isinstance(provider_code, str)
            and len(provider_code) == 5
            and provider_code.isdecimal()
        ):
            provider_code = "unknown"

        print(
            "[失败] amap_business_error："
            f"infocode={provider_code}。"
        )
        return 1

    if status != "1":
        print(
            "[失败] amap_response_invalid："
            "高德业务状态字段不符合预期。"
        )
        return 1

    pois = payload.get("pois")

    if not isinstance(pois, list):
        print(
            "[失败] amap_response_invalid："
            "pois 字段应为列表。"
        )
        return 1

    if any(not isinstance(poi, dict) for poi in pois):
        print(
            "[失败] amap_response_invalid："
            "POI 列表中的记录应为 JSON 对象。"
        )
        return 1

    # 本步用于观察接口，因此保留选中字段的原始值。
    # 没有提供的字段不补造内容。
    selected_pois = [
        {
            "poi_id": poi.get("id"),
            "name": poi.get("name"),
            "address": poi.get("address"),
            "location": poi.get("location"),
        }
        for poi in pois
    ]

    result = {
        "source": "amap",
        "coordinate_system": "GCJ-02",
        # 记录本次查询完成时间，使用带时区的 UTC 时间。
        # 这不是高德数据本身的更新时间。
        "queried_at": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "keyword": keyword,
        "returned_count": len(selected_pois),
        "pois": selected_pois,
    }

    print(
        "[通过] 高德查询成功，"
        f"本页返回 {len(selected_pois)} 条 POI。"
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    if not selected_pois:
        print("[提示] 本次没有匹配结果，请检查城市和关键词。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())