"""FastAPI contract checks without real provider credentials."""

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.app as app_module
from backend.schemas import ResearchRequest, ResearchResponse, SchoolIdentity


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app_module.app)

    def test_serves_desktop_page_and_public_config_without_keys(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "", "DEEPSEEK_API_KEY": ""}):
            page = self.client.get("/")
            config = self.client.get("/api/config")
        self.assertEqual(page.status_code, 200)
        self.assertIn("school-search", page.text)
        self.assertEqual(config.status_code, 200)
        self.assertFalse(config.json()["tavily_configured"])
        self.assertFalse(config.json()["deepseek_configured"])
        self.assertEqual(config.json()["default_model"], "deepseek-flash")

    def test_requires_both_provider_keys(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "", "DEEPSEEK_API_KEY": ""}):
            missing_tavily = self.client.post("/api/research", json={"school_name": "示例大学"})
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tavily-server", "DEEPSEEK_API_KEY": ""}):
            missing_deepseek = self.client.post(
                "/api/research",
                json={"school_name": "示例大学"},
            )
        self.assertEqual(missing_tavily.status_code, 400)
        self.assertEqual(missing_tavily.json()["detail"]["service"], "tavily")
        self.assertEqual(missing_deepseek.status_code, 400)
        self.assertEqual(missing_deepseek.json()["detail"]["service"], "llm")

    def test_success_response_does_not_echo_keys(self):
        result = ResearchResponse(
            school=SchoolIdentity(name="示例大学"),
            summary="暂无通知",
            notices=[],
            queries=["示例大学 通知 公告"],
        )
        with patch.dict(os.environ, {
            "TAVILY_API_KEY": "tavily-server",
            "DEEPSEEK_API_KEY": "deepseek-server",
            "DEEPSEEK_MODEL": "deepseek-test",
        }):
            with patch.object(app_module, "research_notices", new_callable=AsyncMock, return_value=result) as research_mock:
                response = self.client.post(
                    "/api/research",
                    json={"school_name": "示例大学"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"], "暂无通知")
        self.assertEqual(research_mock.await_args.args[1:4], (
            "tavily-server", "deepseek-server", "deepseek-test",
        ))
        self.assertNotIn("tavily-server", response.text)
        self.assertNotIn("deepseek-server", response.text)

    def test_rejects_client_service_configuration(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tavily-server", "DEEPSEEK_API_KEY": "deepseek-server"}):
            with patch.object(app_module, "research_notices", new_callable=AsyncMock) as research_mock:
                response = self.client.post(
                    "/api/research",
                    json={"school_name": "示例大学", "tavily_api_key": "tavily-client"},
                )
        self.assertEqual(response.status_code, 422)
        research_mock.assert_not_awaited()


class ResearchCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_disconnect_cancels_provider_work(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def slow_research(*args):
            started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        async def is_disconnected():
            await started.wait()
            return True

        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key", "DEEPSEEK_API_KEY": "test-key"}):
            with patch.object(app_module, "research_notices", side_effect=slow_research):
                with self.assertRaises(HTTPException) as error:
                    await app_module.research(
                        ResearchRequest(school_name="示例大学"),
                        SimpleNamespace(is_disconnected=AsyncMock(side_effect=is_disconnected)),
                    )
        self.assertEqual(error.exception.status_code, 499)
        self.assertTrue(cancelled.is_set())


if __name__ == "__main__":
    unittest.main()
