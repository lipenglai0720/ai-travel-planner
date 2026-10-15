"""使用本地 JSON 样例验证旅行草案模型。"""

import argparse
import json

from pydantic import ValidationError

from app.models.trip import TripDraft


# 手工编写的学习样例，不是模型返回，也不是已核实的旅行安排。
SAMPLE_DRAFT_JSON = """
{
  "title": "北京三日旅行草案",
  "summary": "以历史文化、美食和轻松游览为主题，具体地点待查询。",
  "days": [
    {
      "date": "2026-11-01",
      "theme": "历史文化",
      "activities": [
        {
          "period": "morning",
          "title": "历史文化主题游览",
          "description": "围绕历史文化安排活动，具体景点和开放信息待查询。"
        }
      ]
    },
    {
      "date": "2026-11-02",
      "theme": "本地饮食文化",
      "activities": [
        {
          "period": "afternoon",
          "title": "饮食文化体验",
          "description": "根据兴趣选择饮食体验，具体商家和费用待查询。"
        }
      ]
    },
    {
      "date": "2026-11-03",
      "theme": "轻松游览",
      "activities": [
        {
          "period": "morning",
          "title": "轻松步行活动",
          "description": "选择适合轻松步行的活动，具体路线和天气待查询。"
        }
      ]
    }
  ]
}
"""


def main() -> int:
    """验证正常样例，或者根据参数验证异常样例。

    返回值：
        0：草案 JSON 通过校验。
        1：草案 JSON 被校验规则拒绝。
    """
    parser = argparse.ArgumentParser(
        description="使用本地 JSON 样例验证旅行草案模型。",
    )
    parser.add_argument(
        "--invalid",
        action="store_true",
        help="使用同一天重复安排上午活动的异常样例。",
    )
    args = parser.parse_args()

    draft_json = SAMPLE_DRAFT_JSON

    if args.invalid:
        # 先将正常 JSON 转成字典，再故意增加一个重复时段。
        sample_data = json.loads(SAMPLE_DRAFT_JSON)

        sample_data["days"][0]["activities"].append(
            {
                "period": "morning",
                "title": "另一个上午活动",
                "description": "用于验证重复时段的异常测试数据。",
            }
        )

        draft_json = json.dumps(
            sample_data,
            ensure_ascii=False,
        )

    try:
        # 同时完成 JSON 解析、嵌套模型转换和业务规则校验。
        draft = TripDraft.model_validate_json(draft_json)
    except ValidationError as exc:
        print("[拒绝] 草案 JSON 未通过校验。")

        # 只显示错误位置、类型和说明。
        for error in exc.errors(
            include_input=False,
            include_context=False,
        ):
            field_path = ".".join(
                str(part) for part in error["loc"]
            ) or "draft"

            print(
                f" - {field_path}: {error['type']}，"
                f"{error['msg']}"
            )

        return 1

    print("[通过] 草案 JSON 校验完成。")
    print(f"草案标题：{draft.title}")
    print(f"旅行天数：{len(draft.days)}")
    print(
        "首日日期类型："
        f"{type(draft.days[0].date).__name__}"
    )

    # 校验后可以再次序列化成 JSON。
    # Python 日期对象会被转换回日期字符串。
    print(draft.model_dump_json(indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
