"""Search official school domains with Tavily."""

from urllib.parse import urlsplit
import ipaddress

import httpx

from backend.schemas import SchoolIdentity

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class UpstreamError(Exception):
    def __init__(self, service: str, message: str):
        super().__init__(message)
        self.service = service
        self.message = message


def source_allowed(url: str, domain: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        return False
    if host == "localhost" or host.endswith((".localhost", ".local")) or "." not in host:
        return False
    try:
        if not ipaddress.ip_address(host).is_global:
            return False
    except ValueError:
        pass
    return not domain or host == domain or host.endswith("." + domain)


async def search_query(
    client: httpx.AsyncClient,
    api_key: str,
    school: SchoolIdentity,
    query: str,
) -> list[dict]:
    collected: dict[str, dict] = {}
    payload = {
        "query": query,
        "topic": "general",
        "search_depth": "basic",
        "max_results": 10,
        "include_answer": False,
    }
    if school.domain:
        payload["include_domains"] = [school.domain]
    try:
        response = await client.post(
            TAVILY_SEARCH_URL,
            headers={"Authorization": "Bearer " + api_key},
            json=payload,
            timeout=25.0,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError("invalid Tavily response")
    except httpx.HTTPStatusError as error:
        if error.response.status_code in {401, 403}:
            raise UpstreamError("tavily", "Tavily API Key 无效或无权限。") from error
        if error.response.status_code == 429:
            raise UpstreamError("tavily", "Tavily 请求过于频繁，请稍后重试。") from error
        raise UpstreamError("tavily", "Tavily 检索失败，请稍后重试。") from error
    except (httpx.HTTPError, ValueError) as error:
        raise UpstreamError("tavily", "无法连接 Tavily 或读取检索结果。") from error

    for item in data.get("results", []):
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not source_allowed(url, school.domain):
            continue
        title = str(item.get("title") or "未命名通知").strip()
        snippet = str(item.get("content") or "").strip()
        if not title and not snippet:
            continue
        canonical = url.split("#", 1)[0].rstrip("/")
        try:
            score = float(item.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        candidate = {"title": title[:240], "url": url, "content": snippet[:2200], "score": score}
        if canonical not in collected or score > collected[canonical]["score"]:
            collected[canonical] = candidate
    ranked = sorted(collected.values(), key=lambda item: item["score"], reverse=True)
    return ranked[:8]
