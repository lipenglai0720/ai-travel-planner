"""手动验证行政区解析与 adcode 查询。"""

import argparse

from pydantic import ValidationError

from app.clients.amap import AmapClient, AmapError
from app.core.config import Settings
from app.models.district import DistrictQuery


def print_amap_error(exc: AmapError) -> None:
    """只打印客户端整理后的错误信息。"""
    print(f"[失败] {exc.code}：{exc}")

    if exc.provider_code is not None:
        print(f"高德错误码：{exc.provider_code}")


def main() -> int:
    """执行一次查询，并返回进程退出码。"""

    parser = argparse.ArgumentParser(
        description="查询行政区名称对应的高德 adcode。",
    )

    parser.add_argument(
        "--keyword",
        default="北京",
        help="行政区名称、城市简称或六位 adcode。",
    )

    parser.add_argument(
        "--province-adcode",
        default=None,
        help="可选的省或直辖市级别 adcode。",
    )

    args = parser.parse_args()

    try:
        # 先验证查询输入。
        # 如果输入不合法，就不继续读取配置和发送请求。
        query = DistrictQuery(
            keyword=args.keyword,
            province_adcode=args.province_adcode,
        )

        settings = Settings()

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
            api_key=settings.amap_web_api_key,
            timeout_seconds=settings.amap_timeout_seconds,
        )
    except AmapError as exc:
        print_amap_error(exc)
        return 2

    try:
        result = client.resolve_district(query)
    except AmapError as exc:
        print_amap_error(exc)
        return 1
    finally:
        # 成功或失败，都释放客户端的连接资源。
        client.close()

    print("[通过] 行政区解析完成。")
    print(result.model_dump_json(indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())