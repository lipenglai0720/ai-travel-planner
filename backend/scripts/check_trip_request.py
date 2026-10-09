"""验证旅行请求的正常输入、类型转换和异常输入拒绝行为。"""

from datetime import date

from pydantic import ValidationError

from app.models.requests import TripRequest


def main() -> None:
    """运行验证案例；检查失败时抛出异常，使脚本执行失败。"""

    # 模拟未来前端提交的数据。
    # 日期在原始字典中是字符串，模型会将其转换为 date 对象。
    raw_data = {
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

    # model_validate 接收输入数据，并返回经过校验的模型对象。
    # 不符合规则时，它会抛出 ValidationError。
    request = TripRequest.model_validate(raw_data)

    # 除了成功创建模型，还检查规范化和日期转换的结果。
    if request.destination != "北京":
        raise RuntimeError("目的地没有按预期去除首尾空白。")

    if not isinstance(request.start_date, date):
        raise RuntimeError("开始日期没有转换为 date 对象。")

    print("正常输入：校验通过")
    print(f"开始日期的 Python 类型：{type(request.start_date).__name__}")
    print(request.model_dump_json(indent=2))

    # 每个案例包含：案例名称、要修改的字段、异常值。
    # 每次只改变一个字段，便于确认错误来自哪里。
    invalid_cases = [
        ("人数为 0", "travelers", 0),
        ("布尔值人数", "travelers", True),
        ("字符串人数", "travelers", "2"),
        ("预算为 0", "budget_cents", 0),
        ("布尔值预算", "budget_cents", True),
        ("浮点数预算", "budget_cents", 600000.0),
        ("空白目的地", "destination", "   "),
        ("无效交通方式", "transportation", "teleport"),
        ("不存在的日期", "start_date", "2026-02-30"),
        ("未定义字段", "days", 999),
    ]

    for case_name, field_name, invalid_value in invalid_cases:
        # 复制输入字典，避免一个异常案例影响后面的案例。
        invalid_data = raw_data.copy()
        invalid_data[field_name] = invalid_value

        try:
            TripRequest.model_validate(invalid_data)
        except ValidationError as exc:
            # errors() 提供结构化错误信息。
            # loc 表示错误位置；本脚本的案例都是顶层字段错误。
            first_error = exc.errors(include_url=False)[0]

            # 单元素元组写成 (field_name,)，末尾逗号不能省略。
            if first_error["loc"] != (field_name,):
                raise RuntimeError(
                    f"案例“{case_name}”报错位置不符合预期："
                    f"{first_error['loc']}"
                ) from exc

            print(
                f"异常输入已拒绝：{case_name}；"
                f"字段：{field_name}"
            )
        else:
            # try 没有发生异常时，才会进入 else。
            # 对异常输入而言，这意味着模型没有拒绝它。
            raise RuntimeError(
                f"案例“{case_name}”被接受，字段校验未达到预期。"
            )

    print(
        f"验证完成：1 个正常案例和 "
        f"{len(invalid_cases)} 个异常案例全部通过。"
    )


# 通过 python -m scripts.check_trip_request 执行时调用 main。
# 其他模块仅导入这个文件时，不会自动运行验证案例。
if __name__ == "__main__":
    main()