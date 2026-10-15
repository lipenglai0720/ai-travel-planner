"""验证城市解析与高德实况天气查询。"""

import argparse

from pydantic import ValidationError

from app.clients.amap import AmapClient, AmapError
from app.core.config import Settings
from app.models.location import DistrictQuery
from app.models.weather import WeatherQuery


def print_amap_error(exc: AmapError) -> None:
    """只打印客户端整理后的错误信息。"""
    print(f"[失败] {exc.code}：{exc}")

    if exc.provider_code is not None:
        print(f"高德错误码：{exc.provider_code}")


def main() -> int:
    """执行一次城市天气查询，并返回退出码。"""

    parser = argparse.ArgumentParser(
        description="先解析行政区，再查询高德实况天气。",
    )

    parser.add_argument(
        "--city",
        default="北京",
        help="城市或区县名称，也可以填写六位 adcode。",
    )

    parser.add_argument(
        "--province-adcode",
        default=None,
        help="可选的省或直辖市编码，用于缩小行政区查询范围。",
    )

    args = parser.parse_args()

    try:
        district_query = DistrictQuery(
            keyword=args.city,
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
        # 第一次请求：使用上一节的功能解析行政区。
        district = client.resolve_district(
            district_query
        )

        # 编码来自经过校验的行政区结果。
        weather_query = WeatherQuery(
            adcode=district.region.adcode,
        )

        # 第二次请求：查询该编码对应的实况天气。
        weather = client.get_current_weather(
            weather_query
        )

    except AmapError as exc:
        print_amap_error(exc)
        return 1
    finally:
        # 两次请求共用一个客户端，结束时统一关闭。
        client.close()

    print("[通过] 实况天气查询及数据校验完成。")

    print(
        "行政区解析："
        f"{district.region.name}"
        f"（{district.region.adcode}）"
    )

    print(weather.model_dump_json(indent=2))

    print(
        "[说明] reported_at 的时区未提供；"
        "本次尚未计算天气数据年龄。"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
