"""验证 LangChain 的消息对象与 DeepSeek 模型调用。"""

import argparse
from time import perf_counter

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_deepseek import ChatDeepSeek
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
)
from pydantic import ValidationError

from app.core.config import Settings


def build_messages() -> list[BaseMessage]:
    """创建本次调用需要的消息列表。

    返回值：
        按发送顺序排列的消息对象。

    这里只创建 Python 对象，不发送网络请求。
    """
    return [
        SystemMessage(
            content="你是一名旅行规划学习助手。请使用简洁中文回答。"
        ),
        HumanMessage(
            content="请用一句话说明制定旅行计划需要考虑哪些因素。"
        ),
    ]


def get_reply_text(reply: AIMessage) -> str:
    """检查模型是否正常完成，并提取可使用的回复文本。

    参数：
        reply：LangChain 返回的 AIMessage。

    返回值：
        去除首尾空白后的回复文本。

    异常：
        ValueError：模型没有正常完成，或者没有返回有效文本。
    """
    # HTTP 请求成功，并不意味着模型输出一定完整。
    # 例如 finish_reason 为 length，可能表示输出被 token 上限截断。
    finish_reason = reply.response_metadata.get("finish_reason")

    if finish_reason != "stop":
        raise ValueError(
            f"模型未正常完成输出，结束原因：{finish_reason}"
        )

    # text 是消息对象提供的属性。
    # 当 content 是字符串时，它读取字符串；
    # 当 content 是内容块列表时，它提取其中的文本内容。
    text = reply.text.strip()

    if not text:
        raise ValueError("模型没有返回可使用的文本。")

    return text


def main() -> int:
    """运行配置检查或一次真实模型调用。

    返回值：
        0：检查或调用成功。
        1：模型调用、响应处理或输出检查失败。
        2：本地配置检查失败。
    """
    parser = argparse.ArgumentParser(
        description="验证 LangChain 的消息对象与 DeepSeek 调用。"
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="只检查本地配置和消息对象，不发送模型请求。",
    )
    args = parser.parse_args()

    # 使用上一节创建的 Settings，继续从环境变量和 .env 读取配置。
    try:
        settings = Settings()
    except ValidationError as exc:
        print("[失败] 配置未通过校验，请检查以下字段：")

        # 仅显示字段路径和错误类型，避免把配置原始值打印出来。
        for error in exc.errors(
            include_input=False,
            include_context=False,
        ):
            field_path = ".".join(
                str(part) for part in error["loc"]
            ) or "settings"
            print(f" - {field_path}: {error['type']}")

        return 2

    # SecretStr 会遮盖常规打印结果。
    # 调用服务商时，需要提取真实字符串，但不把它输出到终端。
    api_key = ""

    if settings.llm_api_key is not None:
        api_key = settings.llm_api_key.get_secret_value().strip()

    if not api_key:
        print("[失败] 缺少 LLM_API_KEY，请检查本地配置。")
        return 2

    messages = build_messages()

    if args.check_config:
        print("[通过] 本地配置和消息对象检查完成，未发送网络请求。")
        print(f"配置模型：{settings.llm_model}")

        for index, message in enumerate(messages, start=1):
            print(
                f"消息 {index}：{type(message).__name__}，"
                f"type={message.type}"
            )

        return 0

    started_at = perf_counter()

    try:
        # ChatDeepSeek 负责把 LangChain 消息转换为 DeepSeek API 请求，
        # 再把服务端响应转换成 AIMessage。
        llm = ChatDeepSeek(
            api_key=api_key,
            base_url=str(settings.llm_base_url),
            model=settings.llm_model,
            temperature=0.2,
            max_tokens=256,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
            streaming=False,
            use_responses_api=False,
            extra_body={
                "thinking": {
                    "type": "disabled",
                }
            },
        )

        # invoke 是同步调用：
        # 当前代码会等待请求完成，然后获得模型返回的消息对象。
        reply = llm.invoke(messages)

    except APITimeoutError:
        # 超时异常属于连接异常的一种，应放在连接异常之前捕获。
        print("[失败] 请求超时，请检查网络和服务状态。")
        return 1

    except APIConnectionError:
        print("[失败] 无法连接模型服务，请检查地址、网络和代理设置。")
        return 1

    except APIStatusError as exc:
        # 只输出状态码，不直接打印第三方返回的完整错误内容。
        print(f"[失败] 模型服务返回 HTTP {exc.status_code}。")
        print("请根据状态码检查请求参数、API Key、余额或服务状态。")
        return 1

    except APIError as exc:
        print(
            "[失败] 底层 SDK 处理请求时出现异常："
            f"{type(exc).__name__}"
        )
        return 1

    except (ValueError, TypeError, KeyError) as exc:
        # 适配器在处理配置或响应格式时也可能失败。
        # 这里只记录异常类型，保留进一步排查的方向。
        print(
            "[失败] 模型适配器处理配置或响应时出现异常："
            f"{type(exc).__name__}"
        )
        return 1

    elapsed_seconds = perf_counter() - started_at

    if not isinstance(reply, AIMessage):
        print("[失败] 模型适配器没有返回预期的 AIMessage。")
        return 1

    try:
        text = get_reply_text(reply)
    except ValueError as exc:
        # 这里的异常消息由我们自己的输出检查函数生成。
        print(f"[失败] {exc}")
        return 1

    print("[通过] LangChain 单次调用完成。")
    print(f"请求模型：{settings.llm_model}")
    print(
        "返回模型："
        f"{reply.response_metadata.get('model_name') or '未返回'}"
    )
    print(f"返回对象类型：{type(reply).__name__}")
    print(
        "结束原因："
        f"{reply.response_metadata.get('finish_reason')}"
    )
    print(f"本次调用耗时：{elapsed_seconds:.2f} 秒")
    print(f"模型回复：{text}")

    # LangChain 将服务商的 token 用量整理成统一字段。
    # 未返回用量时，明确显示“未返回”，避免将未知值当作 0。
    usage = reply.usage_metadata

    if usage is None:
        print("token 用量：服务端未返回。")
    else:
        print(f"输入 token：{usage.get('input_tokens', '未返回')}")
        print(f"输出 token：{usage.get('output_tokens', '未返回')}")
        print(f"总 token：{usage.get('total_tokens', '未返回')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())