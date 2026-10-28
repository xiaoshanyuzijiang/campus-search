"""Read one discovered notice and collect attachment links."""

import re
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from backend.tools.files import fetch_public, is_file_link
from backend.tools.search import TAVILY_SEARCH_URL, source_allowed

TAVILY_EXTRACT_URL = TAVILY_SEARCH_URL.rsplit("/", 1)[0] + "/extract"


def extract_page(data: bytes, url: str, domain: str) -> dict:
    soup = BeautifulSoup(data, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup.select("script, style, nav, footer, form, noscript"):
        tag.decompose()
    article = soup.select_one("article, .v_news_content, #vsb_content, .TRS_Editor, main") or soup.body or soup
    files = []
    seen = set()
    for anchor in article.find_all("a", href=True):
        href = urljoin(url, anchor["href"])
        label = anchor.get_text(" ", strip=True) or anchor.get("title", "")
        if source_allowed(href, domain) and is_file_link(href, label) and href not in seen:
            files.append({"url": href, "title": label or href.rsplit("/", 1)[-1]})
            seen.add(href)
    return {"title": title[:240], "content": article.get_text("\n", strip=True)[:16000], "files": files[:12]}


async def read_notice_page(client: httpx.AsyncClient, api_key: str, url: str, domain: str) -> dict:
    try:
        data, headers, final_url = await fetch_public(client, url, limit=2 * 1024 * 1024)
        if source_allowed(final_url, domain) and "html" in headers.get("content-type", "text/html").lower():
            result = extract_page(data, final_url, domain)
            if result["content"]:
                return result
    except (httpx.HTTPError, ValueError):
        pass
    # A school may block direct requests while Tavily can still read its page.
    response = await client.post(
        TAVILY_EXTRACT_URL,
        headers={"Authorization": "Bearer " + api_key},
        json={"urls": [url], "extract_depth": "basic"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("网页阅读服务返回了无效结果。")
    result = next((item for item in data["results"] if isinstance(item, dict) and item.get("url") == url), {})
    text = result.get("raw_content", "")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("无法读取正文，当前仅保留搜索摘要。")
    files = []
    for label, href in re.findall(r"\[([^\]]*)\]\(([^\s)]+)\)", text):
        href = urljoin(url, href)
        if source_allowed(href, domain) and is_file_link(href, label):
            files.append({"url": href, "title": label})
    return {"title": "", "content": text[:16000], "files": files[:12]}
