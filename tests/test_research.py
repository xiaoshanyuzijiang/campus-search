"""Run the real LangChain graph with scripted provider tool calls, offline."""

import json
import unittest
from io import BytesIO
from unittest.mock import AsyncMock, patch

import httpx
from docx import Document

from backend.agent import research_notices
from backend.schemas import ResearchRequest
from backend.tools.school_identity import official_domain
from backend.tools.search import UpstreamError, source_allowed


def completion(*, text="", tool=None, args=None, call_id="call_1"):
    message = {"role": "assistant", "content": text or None}
    if tool:
        message["tool_calls"] = [{"id": call_id, "type": "function", "function": {"name": tool, "arguments": json.dumps(args or {}, ensure_ascii=False)}}]
    return httpx.Response(200, json={"id": "test-completion", "object": "chat.completion", "created": 1, "model": "test-model",
        "choices": [{"index": 0, "finish_reason": "tool_calls" if tool else "stop", "message": message}]})


class SchoolDomainTests(unittest.TestCase):
    def test_normalizes_website_and_rejects_lookalikes(self):
        self.assertEqual(official_domain("https://www.example.edu.cn/notices"), ("https://www.example.edu.cn/notices", "example.edu.cn"))
        self.assertTrue(source_allowed("https://news.example.edu.cn/notice/1", "example.edu.cn"))
        self.assertFalse(source_allowed("https://example.edu.cn.attacker.test/1", "example.edu.cn"))
        self.assertFalse(source_allowed("javascript:alert(1)", "example.edu.cn"))
        self.assertFalse(source_allowed("http://127.0.0.1/file.pdf", ""))

    def test_rejects_local_hosts(self):
        for site in ("http://localhost/", "http://127.0.0.1/", "http://192.168.1.1/"):
            with self.subTest(site=site), self.assertRaises(ValueError):
                official_domain(site)


class ResearchFlowTests(unittest.IsolatedAsyncioTestCase):
    async def run_agent(self, handler):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("backend.tools.files.validate_public_url", new_callable=AsyncMock):
                return await research_notices(ResearchRequest(school_name="示例大学", website="https://www.example.edu.cn", keywords="奖学金"),
                                              "tavily-test", "llm-test", "test-model", client)

    async def test_model_calls_tools_reads_attachment_then_searches_again(self):
        document = Document()
        document.add_paragraph("奖学金申请表：请在 11 月 1 日前提交成绩单。")
        file = BytesIO()
        document.save(file)
        model_turns = []
        queries = []

        def handler(request):
            if request.url.host == "api.deepseek.com":
                payload = json.loads(request.content)
                model_turns.append(payload)
                self.assertEqual({tool["function"]["name"] for tool in payload["tools"]}, {"search_notices", "read_notice", "read_file"})
                self.assertEqual(payload["thinking"], {"type": "disabled"})
                turn = len(model_turns)
                if turn == 1:
                    return completion(tool="search_notices", args={"query": "奖学金通知"}, call_id="search_1")
                if turn == 2:
                    return completion(tool="read_notice", args={"source_number": 1}, call_id="read_1")
                if turn == 3:
                    return completion(tool="read_file", args={"source_number": 2}, call_id="file_1")
                if turn == 4:
                    self.assertIn("11 月 1 日", json.dumps(payload["messages"], ensure_ascii=False))
                    return completion(tool="search_notices", args={"query": "奖学金申请截止日期"}, call_id="search_2")
                return completion(text="奖学金申请已开放。[1] 申请表要求在 11 月 1 日前提交成绩单。[2]")
            if request.url.path == "/search":
                payload = json.loads(request.content)
                queries.append(payload["query"])
                self.assertEqual(payload["include_domains"], ["example.edu.cn"])
                return httpx.Response(200, json={"results": [
                    {"title": "奖学金通知", "url": "https://news.example.edu.cn/notice/1", "content": "申请已开放", "score": .9},
                    {"title": "伪造来源", "url": "https://example.edu.cn.attacker.test/1", "content": "伪造", "score": 1},
                ]})
            if request.url.path == "/notice/1":
                return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content='<html><title>奖学金申请通知</title><article><p>申请已开放。</p><a href="/files/form.docx">奖学金申请表.docx</a></article></html>'.encode())
            if request.url.path == "/files/form.docx":
                return httpx.Response(200, headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}, content=file.getvalue())
            return httpx.Response(404)

        result = await self.run_agent(handler)
        self.assertEqual(len(model_turns), 5)
        self.assertEqual(len(queries), 2)
        self.assertIn("截止日期", queries[1])
        self.assertEqual([step.tool for step in result.steps], ["search_notices", "read_notice", "read_file", "search_notices"])
        self.assertEqual(len(result.notices), 2)
        self.assertEqual(len(result.files), 1)
        self.assertIn("成绩单", result.files[0].content)
        self.assertEqual(result.files[0].status, "已读取")
        self.assertTrue(result.files[0].download_url.startswith("/api/files/download?token="))
        self.assertNotIn("伪造", result.model_dump_json())

    async def test_empty_search_still_uses_agent_and_does_not_invent_sources(self):
        turns = []
        def handler(request):
            if request.url.host == "api.deepseek.com":
                turns.append(1)
                return completion(tool="search_notices", args={"query": "奖学金"}) if len(turns) == 1 else completion(text="没有找到结果。")
            return httpx.Response(200, json={"results": []})
        result = await self.run_agent(handler)
        self.assertEqual(len(turns), 2)
        self.assertEqual(result.notices, [])
        self.assertIn("未检索到", result.summary)

    async def test_answer_without_search_is_rejected(self):
        with self.assertRaises(UpstreamError) as error:
            await self.run_agent(lambda request: completion(text="凭空生成的通知。"))
        self.assertEqual(error.exception.service, "agent")

    async def test_tavily_auth_error_is_safe(self):
        def handler(request):
            return completion(tool="search_notices", args={"query": "奖学金"}) if request.url.host == "api.deepseek.com" else httpx.Response(401, text="secret upstream detail")
        with self.assertRaises(UpstreamError) as error:
            await self.run_agent(handler)
        self.assertEqual(error.exception.service, "tavily")
        self.assertNotIn("secret", str(error.exception))

    async def test_llm_auth_error_is_safe(self):
        with self.assertRaises(UpstreamError) as error:
            await self.run_agent(lambda request: httpx.Response(401, json={"error": {"message": "secret provider detail", "type": "authentication_error"}}))
        self.assertEqual(error.exception.service, "llm")
        self.assertNotIn("secret", str(error.exception))

    async def test_nonexistent_citation_is_rejected(self):
        turns = []
        def handler(request):
            if request.url.host == "api.deepseek.com":
                turns.append(1)
                return completion(tool="search_notices", args={"query": "奖学金"}) if len(turns) == 1 else completion(text="没有证据的说法。[999]")
            return httpx.Response(200, json={"results": [{"title": "通知", "url": "https://www.example.edu.cn/notice/1", "content": "真实摘要"}]})
        with self.assertRaises(UpstreamError) as error:
            await self.run_agent(handler)
        self.assertEqual(error.exception.service, "agent")


if __name__ == "__main__":
    unittest.main()
