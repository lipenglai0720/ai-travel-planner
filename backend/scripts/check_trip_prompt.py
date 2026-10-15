"""在本地查看旅行需求生成的提示词消息。"""

from app.models.trip import TripRequest
from app.prompts.trip_prompt import (
    TRIP_PROMPT,
    build_trip_messages,
)


def main() -> int:
    """校验示例输入，生成并打印消息。"""
    # 这是用于学习和检查的示例输入。
    # 后续接入接口时，数据将来自用户提交的请求。
    sample_data = {
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

    # 先让 Pydantic 校验字段和业务规则，
    # 再把校验后的对象交给提示词模块。
    trip_request = TripRequest.model_validate(sample_data)

    messages = build_trip_messages(trip_request)

    print("[完成] 旅行需求已转换为消息，本次未调用模型。")
    print(
        "模板变量："
        f"{', '.join(TRIP_PROMPT.input_variables)}"
    )
    print(f"消息数量：{len(messages)}")

    # enumerate 同时提供序号和列表元素。
    # start=1 让打印的消息序号从 1 开始。
    for index, message in enumerate(messages, start=1):
        print(
            f"\n--- 消息 {index}："
            f"{type(message).__name__} ---"
        )
        print(message.text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
