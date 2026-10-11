"""检查模型调用配置，并完成一次 DeepSeek API 调用。"""

import argparse
from time import perf_counter

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
)
from pydantic import ValidationError

from app.core.config import Settings


# 这里只提供排查方向，不直接打印服务端原始错误内容。
HTTP_ERROR_HINTS: dict[int, str] = {
    400: "检查请求格式、模型名称和请求参数。",
    401: "检查是否使用了有效的 DeepSeek API Key。",
    402: "检查 DeepSeek 账号的可用余额。",
    403: "检查账号和模型访问权限。",
    404: "检查服务地址和模型名称。",
    422: "检查服务商要求的请求参数。",
    429: "请求受到限流，请稍后重试。",
    500: "服务商出现内部错误，请稍后重试。",
    503: "服务商当前繁忙，请稍后重试。",
}


def main() -> int:
    """运行检查，返回进程退出码。

    返回值：
        0：本地配置检查通过，或真实模型调用成功。
        1：网络、服务商或模型输出检查失败。
        2：本地配置不合法或缺少 Key。
    """

    parser = argparse.ArgumentParser(
        description="检查配置，并执行一次 DeepSeek 模型调用。",
    )

    parser.add_argument(
        "--check-config",
        action="store_true",
        help="只检查本地配置，不发送网络请求。",
    )

    args = parser.parse_args()

    try:
        settings = Settings()
    except ValidationError as exc:
        print("[失败] 本地配置未通过校验，请检查以下字段：")

        # 只展示字段位置和错误类型，不展示配置输入值。
        for error in exc.errors(
            include_input=False,
            include_context=False,
        ):
            field_path = (
                ".".join(str(part) for part in error["loc"])
                or "settings"
            )

            print(f" - {field_path}: {error['type']}")

        return 2

    # 从 SecretStr 中提取 Key，并去除粘贴时可能产生的首尾空白。
    api_key = ""

    if settings.llm_api_key is not None:
        api_key = settings.llm_api_key.get_secret_value().strip()

    if not api_key:
        print("[失败] 缺少 LLM_API_KEY，请在本地配置中填写有效 Key。")
        return 2

    # 此模式只检查配置读取、类型和 Key 是否填写。
    # Key 是否被服务商接受，需要真实请求才能确认。
    if args.check_config:
        print("[通过] 本地配置检查通过，尚未发送网络请求。")
        print(f"请求模型：{settings.llm_model}")
        return 0

    started_at = perf_counter()

    try:
        # with 在请求处理完成或发生异常后关闭 HTTP 客户端。
        #
        # max_retries=0 关闭 SDK 自动重试，
        # 让本次实验只发起一次生成调用。
        with OpenAI(
            api_key=api_key,
            base_url=str(settings.llm_base_url),
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        ) as client:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一名旅行规划学习助手。"
                            "请使用简洁中文回答。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "请用一句话说明制定旅行计划"
                            "需要考虑哪些因素。"
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=256,
                stream=False,
                # thinking 是 DeepSeek 的扩展参数。
                # 通过 extra_body 传入，并显式使用非思考模式。
                extra_body={
                    "thinking": {
                        "type": "disabled",
                    }
                },
            )

    # 超时异常属于连接异常的一个更具体的类型，
    # 因此先处理超时，再处理其他连接错误。
    except APITimeoutError:
        print("[失败] 模型请求超时，请检查网络和服务状态。")
        return 1

    except APIConnectionError:
        print("[失败] 无法连接模型服务，请检查网络、代理和服务地址。")
        return 1

    except APIStatusError as exc:
        hint = HTTP_ERROR_HINTS.get(
            exc.status_code,
            "请根据服务商文档检查账号和请求参数。",
        )

        print(
            f"[失败] 服务商返回 HTTP {exc.status_code}：{hint}"
        )
        return 1

    except APIError as exc:
        print(
            "[失败] SDK 处理请求或响应时发生错误，"
            f"错误类型：{type(exc).__name__}"
        )
        return 1

    elapsed_seconds = perf_counter() - started_at

    # 网络请求完成后，还需要检查是否得到完整的文本回复。
    if not response.choices:
        print("[失败] 服务端没有返回候选答案。")
        return 1

    choice = response.choices[0]
    content = choice.message.content

    if choice.finish_reason != "stop":
        print(
            "[失败] 模型输出未正常结束，"
            f"结束原因：{choice.finish_reason}"
        )
        return 1

    if not isinstance(content, str) or not content.strip():
        print("[失败] 模型没有返回非空文本。")
        return 1

    print("[通过] DeepSeek 单次调用完成。")
    print(f"请求模型：{settings.llm_model}")
    print(f"返回模型：{response.model}")
    print(f"结束原因：{choice.finish_reason}")
    print(f"本次调用耗时：{elapsed_seconds:.2f} 秒")

    print("模型回复：")
    print(content.strip())

    # 用量以服务端返回
if __name__ == "__main__":
    raise SystemExit(main())