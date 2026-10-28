"""Request-scoped LangChain tools and an authoritative source registry."""

import asyncio
from urllib.parse import urldefrag

import httpx
from langchain.tools import tool

from backend.schemas import Attachment, Notice, SchoolIdentity, ToolStep
from backend.tools.files import extract_document, fetch_public, is_file_link, make_download_url, response_filename
from backend.tools.page_reader import read_notice_page
from backend.tools.search import search_query, source_allowed


class ResearchTools:
    def __init__(self, client: httpx.AsyncClient, tavily_key: str, school: SchoolIdentity):
        self.client = client
        self.tavily_key = tavily_key
        self.school = school
        self.queries: list[str] = []
        self.sources: dict[int, dict] = {}
        self.urls: dict[str, int] = {}
        self.files: dict[int, Attachment] = {}
        self.steps: list[ToolStep] = []
        self.calls = 0

    def _budget(self, name: str, detail: str) -> bool:
        self.calls += 1
        if self.calls > 16:
            return False
        self.steps.append(ToolStep(tool=name, detail=detail[:260]))
        return True

    def _register(self, item: dict, *, source_url: str = "", attachment: bool = False) -> int | None:
        url = urldefrag(item["url"])[0]
        if not source_allowed(url, self.school.domain):
            return None
        if url in self.urls:
            return self.urls[url]
        if len(self.sources) >= 32:
            return None
        number = len(self.sources) + 1
        kind = "file" if attachment or is_file_link(url, item["title"]) else "page"
        self.urls[url] = number
        self.sources[number] = {"number": number, "title": item["title"], "url": url, "content": item.get("content", ""), "kind": kind}
        if kind == "file":
            filename = response_filename(httpx.Headers(), url, item["title"])
            self.files[number] = Attachment(number=number, title=item["title"], url=url, filename=filename, source_url=source_url,
                                             download_url=make_download_url(url, filename, source_url))
        return number

    def as_tools(self) -> list:
        @tool
        async def search_notices(query: str) -> dict:
            """检索当前学校的通知和相关附件。自行选择或调整 query；返回真实 source_number、标题、URL 和搜索摘要。最多搜索四次。"""
            if not self._budget("search_notices", query) or len(self.queries) >= 4:
                return {"error": "已达到检索次数上限，请根据已发现的来源完成整理。"}
            query = query.strip()[:400]
            if not query:
                return {"error": "检索词不能为空。"}
            if self.school.name not in query:
                query = self.school.name + " " + query
            self.queries.append(query)
            results = await search_query(self.client, self.tavily_key, self.school, query)
            sources = []
            for item in results:
                number = self._register(item)
                if number:
                    source = self.sources[number]
                    sources.append({**source, "content": source["content"][:1600]})
            return {"query": query, "sources": sources, "message": "没有找到可用来源，可调整关键词重试。" if not sources else "对重要来源继续调用 read_notice 或 read_file。"}

        @tool
        async def read_notice(source_number: int) -> dict:
            """读取已检索到的通知网页正文，并发现该页的相关附件。source_number 必须来自工具已有的编号；文件请使用 read_file。"""
            if not self._budget("read_notice", "读取来源 [" + str(source_number) + "] 的正文和附件"):
                return {"error": "工具调用已达上限，请完成整理。"}
            source = self.sources.get(source_number)
            if not source:
                return {"error": "该来源编号不存在，请先检索。"}
            if source["kind"] == "file":
                return {"error": "这是文件来源，请调用 read_file。"}
            if source.get("read"):
                return self._page_result(source)
            try:
                page = await read_notice_page(self.client, self.tavily_key, source["url"], self.school.domain)
                source["content"] = page["content"]
                if page["title"]:
                    source["title"] = page["title"]
                source["read"] = True
                source["attachments"] = []
                for item in page["files"]:
                    number = self._register(item, source_url=source["url"], attachment=True)
                    if number:
                        source["attachments"].append(number)
                return self._page_result(source)
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                return {"source_number": source_number, "error": "网页正文读取失败，仅有搜索摘要可用。", "content": source["content"][:1600]}

        @tool
        async def read_file(source_number: int) -> dict:
            """读取已发现的相关文件内容，支持 PDF、DOCX、XLSX、TXT、Markdown、CSV。source_number 来自搜索或 read_notice 返回的附件编号。旧版 DOC/XLS 和压缩包仅提供下载。"""
            if not self._budget("read_file", "读取附件 [" + str(source_number) + "]"):
                return {"error": "工具调用已达上限，请完成整理。"}
            file = self.files.get(source_number)
            if not file:
                return {"error": "附件编号不存在，请先检索或读取其通知网页。"}
            if file.status != "待读取":
                return self._file_result(file)
            try:
                data, headers, final_url = await fetch_public(self.client, file.url, referer=file.source_url)
                if "text/html" in headers.get("content-type", "").lower():
                    raise ValueError("学校返回了网页，文件可能需要登录或已失效。")
                file.filename = response_filename(headers, final_url, file.filename)
                text, status = await asyncio.to_thread(extract_document, data, file.filename)
                file.content = text[:12000]
                file.status = "已读取（仅整理前 12000 字）" if len(text) > 12000 else status
                file.download_url = make_download_url(file.url, file.filename, file.source_url)
                self.sources[source_number]["content"] = file.content
            except Exception as error:
                # Preserve the discovered original even when its format is damaged or protected.
                file.status = str(error) if isinstance(error, ValueError) else "文件读取失败，可尝试下载原文件查看。"
                file.status = file.status[:180]
            return self._file_result(file)

        return [search_notices, read_notice, read_file]

    def _page_result(self, source: dict) -> dict:
        return {"source_number": source["number"], "title": source["title"], "content": source["content"],
                "files": [self._file_result(self.files[number]) for number in source.get("attachments", [])]}

    @staticmethod
    def _file_result(file: Attachment) -> dict:
        return {"source_number": file.number, "title": file.title, "filename": file.filename, "status": file.status, "content": file.content}

    def notices(self) -> list[Notice]:
        return [Notice(**{key: item[key] for key in ("number", "title", "url", "content", "kind")}) for item in self.sources.values()]
