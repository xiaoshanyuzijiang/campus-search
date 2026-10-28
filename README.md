# School Notice

校园通知助手。后端使用 LangChain `create_agent` 和 `ChatDeepSeek`，由模型通过工具调用决定检索词、阅读哪些通知和附件，以及是否需要补充检索，最后生成有来源编号的整理结果。

## 启动

建议使用 Python 3.11+。在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
# 在 .env 中填写 TAVILY_API_KEY 和 DEEPSEEK_API_KEY
.\.venv\Scripts\python -m uvicorn backend.app:app --reload --port 8000
```

打开 `http://localhost:8000`。Tavily 和 DeepSeek 的 Key 统一从服务端环境变量读取；模型由 `DEEPSEEK_MODEL` 指定，默认使用 `deepseek-flash`。页面不接收或发送服务配置。

在 VS Code 中，打开整个 `school_notice` 文件夹，安装 Microsoft Python 和 Python Debugger 扩展，然后在“运行和调试”中选择 `School Notice: FastAPI`，按 F5。配置文件是 `.vscode/launch.json`，使用项目的 `.venv`，启动后会打开浏览器。调试时修改代码需要重新按 F5 启动。

页面支持输入学校中文名，并从 [BadgeSpider 的 Badges 目录](https://github.com/863379105/BadgeSpider/tree/64b499a558c397ca1488ec6bb5d727800040bbd4/Badges)匹配校徽。`ui/assets/badge-catalog.js` 只保存该固定提交的 933 个文件名；图片直接使用 GitHub 原始文件链接，本地不保存校徽图片。学校名称会做空格和全角/半角形式归一化；仓库中没有对应文件或 GitHub 图片无法加载时显示文字占位。页面不再抓取学校官网或调用 Tavily 查找校徽。通知检索仍使用 Tavily，并由 DeepSeek 基于来源撰写摘要，结果下方保留原文链接。

学校卡片会在校徽加载后自动提取主色，背景、边框和缩写标签随之配色。取色只在浏览器内存中完成，不保存校徽图片。

## Agent 与相关文件

Agent 在多轮对话中自主调用三个 LangChain 工具：

- `search_notices(query)`：根据模型选择的检索词查找学校通知和相关文件，官网已填写时限定其域名及子域名。
- `read_notice(source_number)`：读取已发现的网页正文，并收集正文中的附件链接。
- `read_file(source_number)`：读取相关附件，支持 PDF、DOCX、XLSX、TXT、Markdown、CSV。旧版 DOC/XLS、演示文稿和压缩包提供原文件下载；扫描 PDF 无可提取文字时会明确提示。

每次研究独立保存来源编号、附件和工具调用记录，模型只能读取已发现的来源。原文和文件内容中的指令不会成为 Agent 的指令。每次最多搜索 4 次、总工具调用 16 次，整个请求最长 240 秒；停止检索会取消 Agent 请求。单个文件最多读取 12 MB，长文件会显示部分读取提示。

结果页的“相关文件”显示读取状态、内容预览和“下载原文件”按钮。下载由服务端从原始学校网站获取，链接有效期为 6 小时；需要学校登录或已失效的文件会提示失败，并保留原始链接。`FILE_DOWNLOAD_SECRET` 可设置为服务端随机长字符串，使链接在服务重启和多个 worker 间保持有效；未设置时使用当前进程的临时密钥。

## 下载检索结果

检索完成后，标题同行右侧的 **PDF**、**Markdown** 按钮会启用。**PDF 只导出当前学校的通知摘要，不包含原文来源、附件列表和检索记录**，文件名为“学校名称-通知摘要.pdf”。Markdown 导出完整检索结果，包含学校、关键词、摘要、原文内容与链接、相关文件信息和检索词。开始新检索或检索失败时不会导出旧结果。导出无需再次调用模型。

PDF 支持中文、自动分页和页码。摘要中的引用编号（如 `[1]`）可以点击跳转至对应原文，摘要内的网页链接也可点击；不会额外附加原文来源列表。Markdown 中的引用编号同样生成明确的超链接。Windows 自动使用已安装的中文字体；其他系统可通过 `PDF_FONT_PATH` 指定支持中文的 TrueType 字体文件。

## 测试

```powershell
python -m unittest discover -s tests -v
node --test tests/test_badge_theme.cjs
```

测试运行真实的 LangChain Agent 图，并使用模拟的 Tavily、DeepSeek 和学校文件响应，验证多轮工具调用、附件阅读、来源校验、原文件下载及 PDF/Markdown 导出，不消耗 API 配额。
