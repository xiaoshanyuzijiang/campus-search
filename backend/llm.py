"""LangChain DeepSeek model configuration shared by every Agent turn."""

import httpx
from langchain_deepseek import ChatDeepSeek

DEFAULT_MODEL = "deepseek-flash"


def build_model(api_key: str, model: str, client: httpx.AsyncClient) -> ChatDeepSeek:
    return ChatDeepSeek(
        model=model,
        api_key=api_key,
        api_base="https://api.deepseek.com",
        http_async_client=client,
        temperature=0,
        max_tokens=2400,
        timeout=60,
        max_retries=1,
        extra_body={"thinking": {"type": "disabled"}},
    )
