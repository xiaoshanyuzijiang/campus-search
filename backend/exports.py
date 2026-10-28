"""Export the displayed research result to readable Markdown or a Chinese PDF."""

import os
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from html import escape
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from backend.schemas import ResearchResponse
from backend.tools.search import source_allowed

_INLINE_LINK = re.compile(
    r"\[(?P<label>[^\]\n]+)\]\((?P<target>https?://[^\s<>\)]+)\)"
    r"|(?P<url>https?://[^\s<>\[\]，。；！？、（）【】《》]+)"
    r"|\[(?P<citations>\d+(?:\s*[,，、]\s*\d+)*)\]", re.I,
)


def _source_links(result: ResearchResponse) -> dict[int, str]:
    links = {}
    for source in [*result.notices, *result.files]:
        if source_allowed(source.url, ""):
            links.setdefault(source.number, source.url)
    return links


def _linked_text(text: str, sources: dict[int, str], *, pdf: bool = False) -> str:
    """Keep summary wording while adding safe links to references and inline URLs."""
    text = _plain(text)
    plain = escape if pdf else lambda value: value

    def link(label: str, url: str | None) -> str:
        if not url or not source_allowed(url, "") or re.search(r"[\x00-\x20<>]", url):
            return plain(label)
        if pdf:
            return '<link href="' + escape(url, quote=True) + '" color="#2563ba"><u>' + escape(label) + "</u></link>"
        target = quote(url, safe=":/?&=#%+;,@!$'*-._~")
        return "[" + _label(label) + "](" + target + ")"

    parts = []
    cursor = 0
    for match in _INLINE_LINK.finditer(text):
        parts.append(plain(text[cursor:match.start()]))
        if match.group("citations"):
            numbers = match.group("citations")
            if numbers.isdigit():
                parts.append(link(match.group(), sources.get(int(numbers))))
            else:
                parts.append("[" + re.sub(r"\d+", lambda number: link(number.group(), sources.get(int(number.group()))), numbers) + "]")
        elif match.group("target"):
            parts.append(link(match.group("label"), match.group("target")))
        else:
            raw = match.group("url")
            target = raw.rstrip(".,;:!?)]}")
            parts.append(link(target, target) + plain(raw[len(target):]))
        cursor = match.end()
    parts.append(plain(text[cursor:]))
    return "".join(parts)


def _plain(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)


def _label(text: str) -> str:
    return re.sub(r"([\\`*{}\[\]()#+!|])", r"\\\1", _plain(text).replace("\n", " "))


def _time_label(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M") + "（北京时间）"
    except ValueError:
        return value


def result_markdown(result: ResearchResponse) -> str:
    parts = ["# " + _label(result.school.name) + " · 检索结果", "",
             "- 关注关键词：" + _label(result.keywords or "未指定"),
             "- 生成时间：" + _time_label(result.generated_at),
             "- 学校官网：" + _linked_text(result.school.website or "未指定", {}), "", "## 通知摘要", "", _linked_text(result.summary, _source_links(result)), "", "## 原文来源", ""]
    for notice in result.notices:
        parts.extend(["### [" + str(notice.number) + "] " + _label(notice.title), "",
                      "原文：" + _linked_text(notice.url, {}), "", _plain(notice.content) or "暂无可读取正文。", ""])
    if result.files:
        parts.extend(["## 相关文件", ""])
        for file in result.files:
            parts.extend(["### [" + str(file.number) + "] " + _label(file.title), "", "文件名：" + _label(file.filename), "",
                          "读取状态：" + file.status, "", "原文件：" + _linked_text(file.url, {}), "",
                          "所在通知：" + _linked_text(file.source_url, {}) if file.source_url else "直接检索到的文件。", ""])
    parts.extend(["## 检索记录", ""])
    parts.extend("- " + _label(query) for query in result.queries)
    return "\n".join(parts).replace("<", "&lt;").replace(">", "&gt;") + "\n"


@lru_cache(maxsize=1)
def _font() -> str:
    candidates = [os.getenv("PDF_FONT_PATH", ""), "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
                  "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "/System/Library/Fonts/PingFang.ttc"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                pdfmetrics.registerFont(TTFont("SchoolNotice", candidate))
                pdfmetrics.registerFontFamily("SchoolNotice", normal="SchoolNotice", bold="SchoolNotice", italic="SchoolNotice", boldItalic="SchoolNotice")
                return "SchoolNotice"
            except Exception:
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    pdfmetrics.registerFontFamily("STSong-Light", normal="STSong-Light", bold="STSong-Light", italic="STSong-Light", boldItalic="STSong-Light")
    return "STSong-Light"


def result_pdf(result: ResearchResponse) -> bytes:
    font = _font()
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm,
                            topMargin=23 * mm, bottomMargin=22 * mm,
                            title=result.school.name + " · 通知摘要", author="School Notice")
    base = {"fontName": font, "alignment": TA_LEFT, "wordWrap": "CJK", "splitLongWords": True}
    body = ParagraphStyle("Body", fontSize=10, leading=17, textColor=colors.HexColor("#334155"), spaceAfter=7, **base)
    title = ParagraphStyle("Title", fontSize=22, leading=32, textColor=colors.HexColor("#172c48"), spaceAfter=16, **base)
    subheading = ParagraphStyle("Subheading", fontSize=11, leading=18, textColor=colors.HexColor("#172c48"), spaceBefore=12, spaceAfter=7, keepWithNext=True, **base)
    story = []
    sources = _source_links(result)

    def paragraph(text: str, style=body) -> None:
        text = _linked_text(_plain(text), sources, pdf=True)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        story.append(Paragraph(text or " ", style))

    def text_blocks(text: str) -> None:
        for line in _plain(text).splitlines():
            line = line.strip()
            if not line:
                story.append(Spacer(1, 4))
            elif re.match(r"^#{1,6}\s+", line):
                paragraph(re.sub(r"^#{1,6}\s+", "", line), subheading)
            else:
                paragraph(line)

    paragraph(result.school.name + " · 通知摘要", title)
    text_blocks(result.summary)

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dce5f0"))
        canvas.line(20 * mm, 17 * mm, A4[0] - 20 * mm, 17 * mm)
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(20 * mm, 12 * mm, "School Notice · 校园通知整理")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, "第 " + str(document.page) + " 页")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
