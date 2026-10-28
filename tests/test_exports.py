"""Exports contain the current school's actual result, sources, and attachments."""

import unittest
from io import BytesIO
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.app import app
from backend.exports import result_markdown, result_pdf
from backend.schemas import Attachment, Notice, ResearchResponse, SchoolIdentity
from backend.tools.files import make_download_url


def sample_result(long=False):
    return ResearchResponse(
        school=SchoolIdentity(name="四川大学", website="https://www.scu.edu.cn"),
        keywords="奖学金",
        summary="奖学金申请已开放，请于 11 月 1 日前提交材料。[1]\n\n申请表要求填写院系和联系方式。[2]",
        notices=[
            Notice(number=1, title="奖学金申请通知 <2026>", url="https://www.scu.edu.cn/notice/1", content="请按时提交申请材料，并注意截止时间。" * (150 if long else 1)),
            Notice(number=2, title="奖学金申请表.docx", url="https://www.scu.edu.cn/files/form.docx", content="院系、姓名、联系方式。", kind="file"),
        ],
        files=[Attachment(number=2, title="奖学金申请表", filename="奖学金申请表.docx", url="https://www.scu.edu.cn/files/form.docx", source_url="https://www.scu.edu.cn/notice/1", status="已读取", content="院系、姓名、联系方式。")],
        queries=["四川大学 奖学金 通知"],
    )


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_markdown_contains_summary_original_links_and_files(self):
        text = result_markdown(sample_result())
        for expected in ("四川大学", "11 月 1 日", "https://www.scu.edu.cn/notice/1", "form.docx", "相关文件", "检索记录"):
            self.assertIn(expected, text)
        self.assertNotIn("<2026>", text)

    def test_pdf_contains_only_summary_without_sources_or_file_list(self):
        data = result_pdf(sample_result(long=True))
        reader = PdfReader(BytesIO(data))
        self.assertEqual(len(reader.pages), 1)
        text = "\n".join(page.extract_text() for page in reader.pages)
        for expected in ("四川大学", "通知摘要", "奖学金", "11 月 1 日", "联系方式"):
            self.assertIn(expected, text)
        for excluded in ("原文来源", "相关文件", "检索记录", "关注关键词：", "生成时间：", "scu.edu.cn", "奖学金申请表.docx", "请按时提交申请材料"):
            self.assertNotIn(excluded, text)
        links = {str(annotation.get_object()["/A"]["/URI"]) for page in reader.pages for annotation in page.get("/Annots", [])}
        self.assertEqual(links, {"https://www.scu.edu.cn/notice/1", "https://www.scu.edu.cn/files/form.docx"})

    def test_markdown_summary_citations_have_explicit_clickable_links(self):
        text = result_markdown(sample_result())
        self.assertIn(r"[\[1\]](https://www.scu.edu.cn/notice/1)", text)
        self.assertIn(r"[\[2\]](https://www.scu.edu.cn/files/form.docx)", text)

    def test_pdf_keeps_inline_links_and_grouped_citations_clickable(self):
        result = sample_result()
        result.summary = "申请要求。[1, 2]\n[办理入口](https://www.scu.edu.cn/apply?year=2026&kind=1)\n网址：https://www.scu.edu.cn/help。"
        reader = PdfReader(BytesIO(result_pdf(result)))
        links = {str(annotation.get_object()["/A"]["/URI"]) for page in reader.pages for annotation in page.get("/Annots", [])}
        self.assertEqual(links, {"https://www.scu.edu.cn/notice/1", "https://www.scu.edu.cn/files/form.docx", "https://www.scu.edu.cn/apply?year=2026&kind=1", "https://www.scu.edu.cn/help"})
        self.assertIn("办理入口", reader.pages[0].extract_text())

    def test_unknown_citations_and_unsafe_protocols_do_not_create_links(self):
        result = sample_result()
        result.summary = "未知来源。[999]\n[不安全链接](javascript:alert(1))\nhttps://127.0.0.1/private"
        reader = PdfReader(BytesIO(result_pdf(result)))
        self.assertFalse(any(page.get("/Annots") for page in reader.pages))

    def test_long_summary_paginates_without_losing_final_paragraph(self):
        result = sample_result()
        result.summary = "\n\n".join("摘要段落 " + str(i) + "：请在指定时间内提交材料，并关注学院发布的办理要求。" for i in range(100)) + "\n\n摘要结束标记。"
        reader = PdfReader(BytesIO(result_pdf(result)))
        self.assertGreater(len(reader.pages), 1)
        self.assertIn("摘要结束标记", reader.pages[-1].extract_text())

    def test_export_endpoints_download_current_result_without_provider_keys(self):
        for format, content_type, suffix in (("markdown", "text/markdown", ".md"), ("pdf", "application/pdf", ".pdf")):
            with self.subTest(format=format):
                response = self.client.post("/api/export/" + format, json=sample_result().model_dump())
                self.assertEqual(response.status_code, 200)
                self.assertIn(content_type, response.headers["content-type"])
                self.assertIn(suffix, response.headers["content-disposition"])
                self.assertIn("attachment", response.headers["content-disposition"])

    def test_signed_original_file_is_downloaded_and_html_login_is_rejected(self):
        url = make_download_url("https://www.scu.edu.cn/files/form.docx", "申请表.docx")
        with patch("backend.app.fetch_public", new=AsyncMock(return_value=(b"original-file", httpx.Headers({"content-type": "application/octet-stream"}), "https://www.scu.edu.cn/files/form.docx"))):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"original-file")
        self.assertIn("attachment", response.headers["content-disposition"])
        with patch("backend.app.fetch_public", new=AsyncMock(return_value=(b"login", httpx.Headers({"content-type": "text/html"}), "https://www.scu.edu.cn/login"))):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 502)
        self.assertIn("登录", response.json()["detail"]["message"])
        self.assertEqual(self.client.get("/api/files/download?token=bad").status_code, 400)


if __name__ == "__main__":
    unittest.main()
