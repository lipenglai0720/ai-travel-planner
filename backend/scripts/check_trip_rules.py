"""验证旅行日期、天数上限和房间数量的跨字段规则。"""

from pydantic import ValidationError

from app.models.requests import TripRequest


def main() -> None:
    """运行正常与异常案例；结果不符合预期时抛出异常。"""

    base_data = {
        "destination": "北京",
        "start_date": "2026-11-01",
        "end_date": "2026-11-03",
        "travelers": 2,
        "budget_cents": 600000,
        "room_count": 1,
    }

    # 每个正常案例包含：
    # 案例名称、需要替换的输入字段、预期旅行天数。
    normal_cases = [
        (
            "同日旅行",
            {
                "start_date": "2026-11-01",
                "end_date": "2026-11-01",
            },
            1,
        ),
        (
            "跨月旅行",
            {
                "start_date": "2026-10-31",
                "end_date": "2026-11-02",
            },
            3,
        ),
        (
            "跨年旅行",
            {
                "start_date": "2026-12-31",
                "end_date": "2027-01-02",
            },
            3,
        ),
        (
            "闰年跨月旅行",
            {
                "start_date": "2028-02-28",
                "end_date": "2028-03-01",
            },
            3,
        ),
        (
            "恰好 7 天",
            {
                "start_date": "2026-11-01",
                "end_date": "2026-11-07",
            },
            7,
        ),
        (
            "两人预订两间房",
            {"room_count": 2},
            3,
        ),
    ]

    for case_name, changes, expected_days in normal_cases:
        # 每个案例从同一份合法基础数据开始。
        data = base_data.copy()
        data.update(changes)

        request = TripRequest.model_validate(data)

        if request.day_count != expected_days:
            raise RuntimeError(
                f"案例“{case_name}”天数不正确："
                f"预期 {expected_days}，实际 {request.day_count}"
            )

        print(
            f"正常案例通过：{case_name}；"
            f"旅行天数：{request.day_count}"
        )

    # 每个异常案例包含：
    # 案例名称、需要替换的字段、预期错误原因。
    invalid_cases = [
        (
            "日期倒置",
            {
                "start_date": "2026-11-03",
                "end_date": "2026-11-01",
            },
            "结束日期不能早于开始日期",
        ),
        (
            "超过 7 天",
            {
                "start_date": "2026-11-01",
                "end_date": "2026-11-08",
            },
            "旅行天数不能超过 7 天",
        ),
        (
            "房间数超过人数",
            {"room_count": 3},
            "房间数不能超过出行人数",
        ),
    ]

    for case_name, changes, expected_reason in invalid_cases:
        data = base_data.copy()
        data.update(changes)

        try:
            TripRequest.model_validate(data)
        except ValidationError as exc:
            first_error = exc.errors(include_url=False)[0]

            # model_validator 报告的是模型层错误。
            # 此时 loc 是空元组，而不是某个单独字段的名称。
            if first_error["loc"] != ():
                raise RuntimeError(
                    f"案例“{case_name}”错误位置不符合预期："
                    f"{first_error['loc']}"
                ) from exc

            # 检查拒绝原因，避免因为其他错误而误判案例通过。
            if expected_reason not in first_error["msg"]:
                raise RuntimeError(
                    f"案例“{case_name}”错误原因不符合预期："
                    f"{first_error['msg']}"
                ) from exc

            print(
                f"异常案例已拒绝：{case_name}；"
                f"原因：{expected_reason}"
            )
        else:
            raise RuntimeError(
                f"案例“{case_name}”被接受，跨字段校验未达到预期。"
            )

    print(
        f"验证完成：{len(normal_cases)} 个正常案例和 "
        f"{len(invalid_cases)} 个异常案例全部通过。"
    )


if __name__ == "__main__":
    main()