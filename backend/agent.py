"""A LangChain Agent that chooses and executes tools across multiple turns."""

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone

import httpx
from langchain.agents import create_agent
from langgraph.errors import GraphRecursionError
from openai import APIConnectionError, APIStatusError, APITimeoutError

from backend.llm import build_model
from backend.prompts import SYSTEM_PROMPT
from backend.schemas import ResearchRequest, ResearchResponse
from backend.tools.research import ResearchTools
from backend.tools.school_identity import resolve_school
from backend.tools.search import UpstreamError


async def research_notices(
    request: ResearchRequest,
    tavily_key: str,
    llm_key: str,
    model: str,
    client: httpx.AsyncClient,
) -> ResearchResponse:
    school = resolve_school(request)
    tools = ResearchTools(client, tavily_key, school)
    agent = create_agent(
        model=build_model(llm_key, model, client),
        tools=tools.as_tools(),
        system_prompt=SYSTEM_PROMPT,
    )
    task = json.dumps({
        "school": school.model_dump(),
        "keywords": request.keywords.strip(),
        "current_date": datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
        "task": "检索并整理学校通知，阅读相关附件，并为重要发现引用真实来源。",
    }, ensure_ascii=False)
    try:
        result = await asyncio.wait_for(
            agent.ainvoke({"messages": [{"role": "user", "content": task}]}, config={"recursion_limit": 32}),
            timeout=240,
        )
    except APIStatusError as error:
        if error.status_code in {401, 403}:
            raise UpstreamError("llm", "DeepSeek API Key 无效或无权限。") from error
        if error.status_code == 429:
            raise UpstreamError("llm", "DeepSeek 请求过于频繁，请稍后重试。") from error
        raise UpstreamError("llm", "DeepSeek 工具调用失败，请检查模型是否支持工具调用。") from error
    except (APIConnectionError, APITimeoutError) as error:
        raise UpstreamError("llm", "无法连接 DeepSeek，请稍后重试。") from error
    except (asyncio.TimeoutError, GraphRecursionError) as error:
        raise UpstreamError("agent", "本次研究已达到时间或轮次上限，请缩小关注关键词后重试。") from error
    if not tools.queries:
        raise UpstreamError("agent", "模型未执行检索工具，无法提供有来源的结果，请重试。")
    message = result["messages"][-1]
    summary = message.content if isinstance(message.content, str) else "\n".join(block.get("text", "") for block in message.content if isinstance(block, dict))
    if not tools.sources:
        summary = "未检索到可用通知或相关文件。请检查学校官网或更换关键词后重试。"
    elif not summary.strip() or any(int(number) not in tools.sources for number in re.findall(r"\[(\d+)\]", summary)):
        raise UpstreamError("agent", "Agent 未生成有效的来源摘要，请重试。")
    return ResearchResponse(
        school=school,
        summary=summary.strip(),
        notices=tools.notices(),
        queries=tools.queries,
        model=model,
        keywords=request.keywords.strip(),
        files=list(tools.files.values()),
        steps=tools.steps,
    )
