"""FastAPI entry point; serves both the desktop UI and research API."""

import asyncio
import os
from contextlib import suppress
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.agent import research_notices
from backend.exports import result_markdown, result_pdf
from backend.llm import DEFAULT_MODEL
from backend.schemas import ResearchRequest, ResearchResponse
from backend.tools.search import UpstreamError
from backend.tools.files import fetch_public, response_filename, safe_filename, verify_download_token

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"
load_dotenv(ROOT / ".env")

app = FastAPI(title="School Notice API", version="0.1.0")
app.mount("/assets", StaticFiles(directory=UI_DIR / "assets"), name="assets")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/api/config")
async def config() -> dict:
    return {
        "tavily_configured": bool(os.getenv("TAVILY_API_KEY", "").strip()),
        "deepseek_configured": bool(os.getenv("DEEPSEEK_API_KEY", "").strip()),
        "default_model": os.getenv("DEEPSEEK_MODEL", "").strip() or DEFAULT_MODEL,
    }


@app.post("/api/export/{format}")
def export_result(format: Literal["pdf", "markdown"], result: ResearchResponse) -> Response:
    if len(result.model_dump_json()) > 2_000_000 or len(result.notices) > 50 or len(result.files) > 30:
        raise HTTPException(status_code=413, detail={"message": "检索结果过大，无法导出。"})
    extension = ".pdf" if format == "pdf" else ".md"
    filename = safe_filename(result.school.name + ("-通知摘要" if format == "pdf" else "-检索结果") + extension)
    body = result_pdf(result) if format == "pdf" else result_markdown(result).encode("utf-8-sig")
    return Response(body, media_type="application/pdf" if format == "pdf" else "text/markdown; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename)})


@app.get("/api/files/download")
async def download_file(token: str) -> Response:
    try:
        payload = verify_download_token(token)
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"message": str(error)}) from error
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            body, headers, final_url = await fetch_public(client, payload["url"], referer=payload["referer"])
        if "text/html" in headers.get("content-type", "").lower():
            raise ValueError("学校返回了网页，文件可能需要登录或已失效，请打开原文查看。")
        filename = response_filename(headers, final_url, payload["filename"])
        return Response(body, media_type="application/octet-stream", headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename), "X-Content-Type-Options": "nosniff"})
    except (httpx.HTTPError, ValueError) as error:
        message = str(error) if isinstance(error, ValueError) else "暂时无法下载此文件，请打开学校原文后重试。"
        raise HTTPException(status_code=502, detail={"message": message}) from error


@app.post("/api/research", response_model=ResearchResponse)
async def research(request: ResearchRequest, http_request: Request) -> ResearchResponse:
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    llm_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    model = os.getenv("DEEPSEEK_MODEL", "").strip() or DEFAULT_MODEL
    if not tavily_key:
        raise HTTPException(status_code=400, detail={"service": "tavily", "message": "服务端未配置 Tavily API Key，请联系管理员。"})
    if not llm_key:
        raise HTTPException(status_code=400, detail={"service": "llm", "message": "服务端未配置 DeepSeek API Key，请联系管理员。"})
    try:
        async with httpx.AsyncClient(follow_redirects=True, trust_env=False) as client:
            task = asyncio.create_task(research_notices(request, tavily_key, llm_key, model, client))
            disconnected = False

            async def stop_on_disconnect() -> None:
                nonlocal disconnected
                while not task.done():
                    if await http_request.is_disconnected():
                        disconnected = True
                        task.cancel()
                        return
                    await asyncio.sleep(0.25)

            watcher = asyncio.create_task(stop_on_disconnect())
            try:
                return await task
            except asyncio.CancelledError:
                if disconnected:
                    raise HTTPException(status_code=499, detail={"message": "检索已停止。"}) from None
                raise
            finally:
                watcher.cancel()
                with suppress(asyncio.CancelledError):
                    await watcher
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"message": str(error)}) from error
    except UpstreamError as error:
        raise HTTPException(
            status_code=502,
            detail={"service": error.service, "message": error.message},
        ) from error
