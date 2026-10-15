"""使用本地样例检查旅行草案与原始需求的一致性。"""

import argparse
import json
from datetime import date, timedelta

from pydantic import ValidationError

from app.models.trip import (
    TripDraft,
    TripRequest,
)
from app.services.draft_validation import (
    DraftRequestMismatchError,
    validate_draft_matches_request,
)
from scripts.check_trip_draft import SAMPLE_DRAFT_JSON


# 对应上一步三日草案的原始旅行需求。
REQUEST_DATA = {
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


def main() -> int:
    """
    执行本地验证。

    返回值：
        0：草案与需求一致。
        1：草案与需求不一致。
        2：测试数据没有通过基础模型校验。
    """
    parser = argparse.ArgumentParser(
        description="检查旅行草案与原始需求的一致性。",
    )
    parser.add_argument(
        "--case",
        choices=("valid", "missing_day", "shifted_dates"),
        default="valid",
        help="选择正常、缺少一天或日期偏移的测试样例。",
    )
    args = parser.parse_args()

    # 每次运行都从 JSON 创建一份新的样例字典。
    draft_data = json.loads(SAMPLE_DRAFT_JSON)

    if args.case == "missing_day":
        # 删除最后一天。
        # 剩余两天仍然连续，能通过 TripDraft 内部校验，
        # 但不符合用户要求的三天。
        draft_data["days"].pop()

    elif args.case == "shifted_dates":
        # 把每一天都向后移动一天。
        # 三天仍然连续，但范围变成 11 月 2 日至 4 日。
        for day_data in draft_data["days"]:
            original_date = date.fromisoformat(day_data["date"])
            shifted_date = original_date + timedelta(days=1)
            day_data["date"] = shifted_date.isoformat()

    try:
        # 第一步：构建合法的原始需求。
        trip_request = TripRequest.model_validate(REQUEST_DATA)

        # 第二步：检查草案本身的结构。
        #
        # 上一步 DayDraft.date 使用了 strict=True。
        # 这里通过 JSON 校验，使 ISO 日期字符串按 JSON 规则解析。
        draft = TripDraft.model_validate_json(
            json.dumps(draft_data, ensure_ascii=False),
        )

    except ValidationError as exc:
        print("[基础校验失败] 测试数据没有通过 Pydantic 校验。")

        for error in exc.errors(
            include_input=False,
            include_context=False,
        ):
            field_path = ".".join(
                str(part) for part in error["loc"]
            ) or "model"

            print(
                f" - {field_path}: "
                f"{error['type']}，{error['msg']}"
            )

        return 2

    try:
        # 第三步：检查两份已经合法的数据是否互相匹配。
        validate_draft_matches_request(trip_request, draft)

    except DraftRequestMismatchError as exc:
        print("[拒绝] 草案与旅行需求不一致。")
        print(f"错误代码：{exc.code}")
        print(f"错误说明：{exc}")
        return 1

    print("[通过] 草案与旅行需求一致。")
    print(
        f"请求日期：{trip_request.start_date} "
        f"至 {trip_request.end_date}"
    )
    print(
        f"草案日期：{draft.days[0].date} "
        f"至 {draft.days[-1].date}"
    )
    print(f"旅行天数：{len(draft.days)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
