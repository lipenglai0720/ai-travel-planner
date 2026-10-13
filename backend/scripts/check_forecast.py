"""验证短期预报查询与指定日期的覆盖情况。"""

import argparse
from datetime import date

from pydantic import ValidationError

from app.clients.amap import AmapClient, AmapError
from app.core.config import Settings
from app.models.district import DistrictQuery
from app.models.weather import WeatherQuery


def parse_target_date(raw: str | None) -> date | None:
    """解析可选的目标日期，仅接受 YYYY-MM-DD。"""

    if raw is None:
        return None

    value = raw.strip()
    parsed = date.fromisoformat(value)

    if parsed.isoformat() != value:
        raise ValueError("目标日期应使用 YYYY-MM-DD。")

    return parsed


def print_amap_error(exc: AmapError) -> None:
    """打印客户端整理后的错误信息。"""

    print(f"[失败] {exc.code}：{exc}")

    if exc.provider_code is not None:
        print(f"高德错误码：{exc.provider_code}")


def main() -> int:
    """查询预报，并用不同退出码表示执行结果。"""

    parser = argparse.ArgumentParser(
        description="查询短期天气预报，并检查指定日期是否有记录。",
    )

    parser.add_argument(
        "--city",
        default="北京",
        help="城市、区县名称或六位 adcode。",
    )

    parser.add_argument(
        "--province-adcode",
        default=None,
        help="可选的省或直辖市编码。",
    )

    parser.add_argument(
        "--date",
        default=None,
        help="可选的目标日期，格式为 YYYY-MM-DD。",
    )

    args = parser.parse_args()

    try:
        district_query = DistrictQuery(
            keyword=args.city,
            province_adcode=args.province_adcode,
        )

        target_date = parse_target_date(args.date)
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

    except ValueError:
        print("[失败] date_invalid：目标日期应为有效的 YYYY-MM-DD。")
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
        district = client.resolve_district(
            district_query
        )

        forecast = client.get_forecast(
            WeatherQuery(
                adcode=district.region.adcode,
            )
        )

    except AmapError as exc:
        print_amap_error(exc)
        return 1

    finally:
        client.close()

    print("[通过] 预报查询及数据校验完成。")

    available_dates = "、".join(
        item.forecast_date.isoformat()
        for item in forecast.days
    )

    print(f"可用日期：{available_dates}")
    print(forecast.model_dump_json(indent=2))

    print(
        "[说明] 这些数据属于供应商预报，实际天气可能变化；"
        "发布时间的时区未提供，本次未计算数据年龄。"
    )

    if target_date is None:
        return 0

    selected_day = forecast.find_day(target_date)

    if selected_day is None:
        print(
            f"[未覆盖] 当前返回数据中没有 "
            f"{target_date.isoformat()} 的预报。"
        )
        return 3

    print(
        f"[覆盖] 当前返回数据中包含 "
        f"{target_date.isoformat()} 的预报。"
    )
    print(selected_day.model_dump_json(indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())