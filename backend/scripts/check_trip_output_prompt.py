"""在本地检查带有旅行草案输出结构的提示词。"""

import argparse

from app.models.requests import TripRequest
from app.prompts.trip_prompt import (
    TRIP_PROMPT,
    build_trip_messages,
)


def main() -> int:
    """
    执行提示词检查。

    返回值：
        0：正常生成提示词。
        1：异常样例触发了预期的缺少变量错误。
        2：异常样例没有触发应有的错误。
    """
    parser = argparse.ArgumentParser(
        description="检查旅行提示词中的 JSON 输出结构。",
    )
    parser.add_argument(
        "--missing-input",
        action="store_true",
        help="故意不提供旅行需求，检查缺少模板变量的错误。",
    )
    args = parser.parse_args()

    if args.missing_input:
        try:
            # Schema 已提前绑定，但旅行需求仍然必须提供。
            # 这里故意省略 trip_request_json。
            TRIP_PROMPT.format_messages()

        except KeyError as exc:
            print("[预期异常] 提示词缺少必需变量。")
            print(f"缺少的变量：{exc.args[0]}")
            return 1

        print("[检查失败] 缺少旅行需求时，模板没有报告错误。")
        return 2

    # 构建一份正常的旅行需求。
    trip_request = TripRequest.model_validate(
        {
            "destination": "北京",
            "start_date": "2026-11-01",
            "end_date": "2026-11-03",
            "travelers": 2,
            "budget_cents": 600000,
            "transportation": "public_transit",
            "accommodation_preference": "economy",
            "room_count": 1,
            "preferences": ["历史文化", "本地美食"],
            "pace": "relaxed",
        }
    )

    messages = build_trip_messages(trip_request)

    print("[通过] 已生成包含输出结构的旅行提示词。")
    print(f"消息数量：{len(messages)}")
    print(f"消息类型：{[message.type for message in messages]}")
    print(f"仍需输入的模板变量：{TRIP_PROMPT.input_variables}")

    # 查看两条消息的完整文本，方便确认 Schema 和需求的位置。
    for index, message in enumerate(messages, start=1):
        print()
        print(f"消息 {index}：{type(message).__name__}")
        print(message.content)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())