# School Notice · 校园通知助手

输入学校和关注的主题，查找分散在学校网站上的通知，阅读原文及附件，并生成带来源编号的摘要。

## 目录

- [项目简介](#项目简介)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [使用方法](#使用方法)
- [工作原理](#工作原理)
- [下载与导出](#下载与导出)
- [项目结构](#项目结构)
- [测试](#测试)
- [校徽来源](#校徽来源)

## 项目简介

School Notice 使用 Tavily 检索校园通知，使用 DeepSeek 和 LangChain Agent 选择检索词、阅读通知正文与附件，再整理成可追溯到原文的结果。页面提供学校选择、可选的官网域名和关键词输入，以及 PDF、Markdown 导出。

主要功能：

- 按学校名称和关键词检索；填写学校官网时，将检索限定在该域名及其子域名。
- 展示通知摘要、原文链接、相关文件和检索过程；摘要中的引用编号对应原文。
- 阅读 PDF、DOCX、XLSX、TXT、Markdown、CSV 附件，并提供原文件下载。
- 匹配校徽并为学校卡片提取配色；校徽缺失或无法加载时显示文字占位。
- 停止正在进行的检索，或将结果导出为 PDF / Markdown。

## 技术栈

- **后端：** Python、FastAPI、Uvicorn
- **检索与 Agent：** Tavily、LangChain、LangGraph、DeepSeek
- **文件处理与导出：** pypdf、python-docx、openpyxl、ReportLab
- **前端：** 原生 HTML、CSS、JavaScript，由 FastAPI 提供静态文件

依赖版本范围见 [requirements.txt](./requirements.txt)。前端无需单独安装依赖或构建。

## 快速开始

### 准备

- 建议使用 Python 3.11 或更新版本。
- 准备 Tavily API Key 和 DeepSeek API Key。
- 如需运行校徽主题的 JavaScript 测试，另需安装 Node.js。

克隆仓库后进入项目目录：

~~~text
git clone https://github.com/xiaoshanyuzijiang/school_notice.git
cd school_notice
~~~

### Windows PowerShell

~~~powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env，填写 TAVILY_API_KEY 和 DEEPSEEK_API_KEY
.\.venv\Scripts\python -m uvicorn backend.app:app --reload --port 8000
~~~

### macOS / Linux

~~~bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填写 TAVILY_API_KEY 和 DEEPSEEK_API_KEY
.venv/bin/python -m uvicorn backend.app:app --reload --port 8000
~~~

启动后打开 http://localhost:8000。密钥只从服务端环境变量读取，页面不接收或发送服务配置。[.env.example](./.env.example) 列出所有配置项：

| 配置项 | 用途 |
| --- | --- |
| TAVILY_API_KEY | 通知检索，必填 |
| DEEPSEEK_API_KEY | Agent 与摘要生成，必填 |
| DEEPSEEK_MODEL | 可选，默认 deepseek-flash |
| FILE_DOWNLOAD_SECRET | 可选，使原文件下载链接在重启和多 worker 间保持有效 |
| PDF_FONT_PATH | 可选，非 Windows 系统上指定支持中文的 TrueType 字体 |

在 VS Code 中也可以打开整个 school_notice 文件夹，安装 Microsoft Python 和 Python Debugger 扩展，在“运行和调试”中选择 **School Notice: FastAPI**，按 F5。配置位于 [.vscode/launch.json](./.vscode/launch.json)，使用项目的 .venv。调试时修改代码需要重新按 F5 启动。

## 使用方法

1. 输入学校中文名，或选择常用学校。
2. 按需填写学校官网与关注关键词；官网用于限定检索来源。
3. 点击“开始检索”。可以在运行期间点击“停止检索”。
4. 阅读摘要、原文来源与相关文件；需要核对细节时打开原文链接。
5. 检索完成后，用结果标题旁的 **PDF** 或 **Markdown** 按钮下载结果。

## 工作原理

Agent 使用三个 LangChain 工具，按检索过程决定下一步：

| 工具 | 作用 |
| --- | --- |
| search_notices(query) | 查找通知和相关文件；填写官网时限定其域名及子域名 |
| read_notice(source_number) | 阅读已发现的网页正文，收集附件链接 |
| read_file(source_number) | 阅读已发现的附件内容 |

每次检索独立保存来源编号、附件和工具调用记录。模型只能读取已发现的来源，网页与文件内容中的指令不会成为 Agent 指令。单次请求最多搜索 4 次、总工具调用 16 次、最长运行 240 秒；单个文件最多读取 12 MB，长文件会提示只读取了部分内容。

旧版 DOC/XLS、演示文稿和压缩包可下载原文件；扫描 PDF 没有可提取文字时会明确提示。需要学校登录或已失效的文件可能无法读取或下载，结果中仍保留原始链接。

## 下载与导出

- **原文件：** 结果页显示相关文件的读取状态、内容预览和“下载原文件”按钮。服务端从原始学校网站获取文件；下载链接有效期为 6 小时。未设置 FILE_DOWNLOAD_SECRET 时使用当前进程的临时密钥。
- **PDF：** 只导出当前学校的通知摘要，不附加原文来源、附件列表或检索记录。支持中文、自动分页和页码；摘要中的引用编号与网页链接可点击。
- **Markdown：** 导出完整结果，包括学校、关键词、摘要、原文内容与链接、相关文件信息和检索词；引用编号会生成明确的超链接。

开始新检索或检索失败时，旧结果的导出按钮不会继续可用。导出不再调用模型。

## 项目结构

~~~text
backend/
  app.py          FastAPI 入口与 API
  agent.py        Agent 检索流程
  tools/          检索、网页和附件读取
  exports.py      PDF 与 Markdown 导出
ui/
  index.html      页面
  assets/         样式、交互与校徽目录
tests/            API、检索、文件、导出及页面主题测试
requirements.txt  Python 依赖
.env.example      环境变量示例
~~~

## 测试

~~~powershell
python -m unittest discover -s tests -v
node --test tests/test_badge_theme.cjs
~~~

Python 测试运行真实的 LangChain Agent 图，使用模拟的 Tavily、DeepSeek 和学校文件响应，覆盖多轮工具调用、附件阅读、来源校验、原文件下载与导出，不消耗 API 配额。

## 校徽来源

学校名称在本地做空格和全角/半角形式归一化，再与 [BadgeSpider 的 Badges 目录](https://github.com/863379105/BadgeSpider/tree/64b499a558c397ca1488ec6bb5d727800040bbd4/Badges)匹配。[ui/assets/badge-catalog.js](./ui/assets/badge-catalog.js) 仅保存该固定提交的 933 个文件名；校徽图片直接从 GitHub 原始文件链接加载，本地不保存图片。图片无法加载时显示文字占位。卡片主色在浏览器内存中提取，不保存图片。
