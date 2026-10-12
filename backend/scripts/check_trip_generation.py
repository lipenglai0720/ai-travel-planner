"""检查旅行草案生成服务。"""

import argparse
from unittest.mock import Mock

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.core.config import Settings
from app.llm.client import (
    LLMConfigurationError,
    create_trip_chat_model,
)
from app.models.requests import TripRequest
from app.services.trip_generation_service import (
    TripGenerationError,
    TripGenerationService,
)


def show_generation(
    service: TripGenerationService,
    trip_request: TripRequest,
) -> int:
    """
    执行生成并展示结果。

    返回值：
        0：生成成功并通过校验。
        1：生成失败或结果被校验拒绝。
    """
    try:
        draft = service.generate_draft(trip_request)

    except TripGenerationError as exc:
        print("[失败] 旅行草案生成失败。")
        print(f"错误代码：{exc.code}")
        print(f"错误说明：{exc}")
        return 1

    print("[通过] 旅行草案生成并通过校验。")
    print(f"草案标题：{draft.title}")
    print(f"旅行天数：{len(draft.days)}")
    print(
        f"日期范围：{draft.days[0].date} "
        f"至 {draft.days[-1].date}"
    )
    print(draft.model_dump_json(indent=2))

    return 0


def main() -> int:
    """选择本地检查或真实模型调用。"""
    parser = argparse.ArgumentParser(
        description="检查旅行草案的生成与校验。",
    )

    # 两个检查选项不能同时使用，避免运行意图不明确。
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check-config",
        action="store_true",
        help="检查配置和客户端初始化，不发送模型请求。",
    )
    group.add_argument(
        "--invalid-output",
        action="store_true",
        help="使用替身模型返回错误 JSON，检查异常处理。",
    )
    args = parser.parse_args()

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

    if args.invalid_output:
        # Mock 是 Python 标准库中的替身对象。
        # 这里只模拟模型的方法和返回值，不创建真实模型客户端。
        fake_model = Mock(spec=BaseChatModel)
        fake_model.invoke.return_value = AIMessage(
            content='{"title":',
            response_metadata={
                "finish_reason": "stop",
            },
        )

        print("[本地异常测试] 使用替身模型返回不完整 JSON。")
        service = TripGenerationService(fake_model)

        return show_generation(service, trip_request)

    try:
        settings = Settings()
        chat_model = create_trip_chat_model(settings)

    except LLMConfigurationError as exc:
        print(f"[配置失败] {exc}")
        return 2

    except ValidationError as exc:
        print("[配置失败] 配置或模型参数未通过校验。")

        for error in exc.errors(
            include_input=False,
            include_context=False,
        ):
            field_path = ".".join(
                str(part) for part in error["loc"]
            ) or "config"

            print(f" - {field_path}: {error['type']}")

        return 2

    try:
        if args.check_config:
            print("[通过] 配置与模型初始化完成，未发送请求。")
            print(f"模型：{settings.llm_model}")
            return 0

        print(f"[真实调用] 模型：{settings.llm_model}")

        service = TripGenerationService(chat_model)
        return show_generation(service, trip_request)

    finally:
        # 当前脚本使用同步调用。
        # 无论生成成功还是失败，都释放同步 HTTP 客户端。
        chat_model.root_client.close()


if __name__ == "__main__":
    raise SystemExit(main())