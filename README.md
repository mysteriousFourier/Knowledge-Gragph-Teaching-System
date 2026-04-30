# Knowledge-Gragph-Teaching-System

Knowledge-Gragph-Teaching-System 是一个本地运行的知识图谱教学系统，用于教师备课、学生学习、知识图谱维护、课堂问答和选择题练习。前端是纯静态 HTML、CSS、JavaScript，后端由多个 FastAPI 服务提供数据、生成和图谱接口。

项目名按公开仓库名称保留为 `Knowledge-Gragph-Teaching-System`。

## 功能概览

- 教师端：章节导入、授课文案生成、题库生成、题目反馈、自然语言补充知识、图谱浏览。
- 学生端：课程内容阅读、练习题作答、侧边问答、答案解析、知识图谱查看、学习路径查询。
- 模型路由：普通问答使用 `flash` 模型；授课文案、题库等深度生成任务使用 `pro` 模型。
- 知识图谱增强：图谱和结构化材料作为优先证据，不再把约束写成过强的拒答规则。
- 题库缓存：题目会预生成并写入运行时章节缓存，避免每次进入练习都重新生成。
- 题目反馈：教师可对题目和选项点赞/点踩；点赞题目保留，点踩题目从候选题库移除，反馈会影响后续生成提示词。
- Markdown 与 LaTeX 渲染：课程内容、授课文案、问答、图谱详情、题目和选项都按统一渲染链路处理。
- 公式展开：支持从 `structured/formula_library.json` 展开 `[[FORMULA:6.35]]`、`[[SEE_FORMULA:6.35]]` 和 `Equation 6.35` 等引用。
- 视觉体验：教师端和学生端使用暗色字符波纹背景，内容区使用低干扰的液态玻璃风格。

## 目录结构

```text
frontend/                    纯静态前端页面和浏览器端脚本
backend/start_all.py          本地服务编排器
backend/frontend_server.py    静态前端服务器，默认端口 3000
backend/education/            教师端/学生端业务 API，默认端口 8001
backend/maintenance/          图谱维护 API，默认端口 8002
backend/vector_index_system/  SQLite 图谱服务、搜索和后台管理页面
backend/mcp-server/           MCP 兼容的图谱工具桥接服务
structured/                   结构化章节、公式和表格数据
scripts/                      启动、停止、检查等辅助脚本
docs/                         维护者文档
data/                         数据说明；生成数据不会提交
```

## 快速开始

1. 复制配置文件：

```bat
copy .env.example .env
```

2. 修改 `.env`。至少需要配置登录信息和 DeepSeek API Key：

```env
APP_STUDENT_USERNAME=student
APP_STUDENT_PASSWORD=change-me
APP_TEACHER_USERNAME=teacher
APP_TEACHER_PASSWORD=change-me

DEEPSEEK_API_KEY=
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
DEEPSEEK_PRO_MODEL=deepseek-v4-pro
```

如果本机 Python 不在 PATH 中，也可以配置：

```env
PYTHON_EXE=
CONDA_ENV_PYTHON=
CONDA_ROOT=
CONDA_ENV_NAME=
```

3. Windows 下启动：

```bat
start.bat
```

启动脚本会生成 `frontend/env-config.js`，启动前端、教育 API、维护 API，并自动打开 `http://localhost:3000/`。

4. 停止服务：

```powershell
powershell -ExecutionPolicy Bypass -File stop.ps1
```

## 页面入口

- 主页：`http://localhost:3000/`
- 教师端：`http://localhost:3000/teacher.html`
- 学生端：`http://localhost:3000/student.html`
- 图谱后台：`http://localhost:3000/backend/vector_index_system/knowledge_graph/backend_admin.html`

## 主要工作流

教师端常用流程：

1. 登录教师端。
2. 导入或选择章节。
3. 生成授课文案。
4. 继续生成题库。
5. 对题目和选项点赞/点踩。
6. 将满意题目保留到题库。

学生端常用流程：

1. 登录学生端。
2. 阅读课程内容和授课文案。
3. 进入练习模式。
4. 点击选项完成选择并查看解析。
5. 在侧边问答中追问公式、概念或图谱关系。

## 公式与 Markdown

前端统一使用 Markdown 渲染器和 LaTeX 渲染器。后端会在返回题目、答案、图谱详情和文案前尽量展开公式引用。推荐结构化材料保留英文原文，避免翻译导致概念或公式含义变化。

如果内容中出现公式编号，应优先写成可解析形式：

```text
[[FORMULA:6.35]]
[[SEE_FORMULA:6.35]]
Equation 6.35
```

系统会尝试从 `structured/formula_library.json` 中取出原公式并显示。

## 数据与隐私

`.gitignore` 已排除本地密钥、运行缓存、数据库、日志、模型文件、外部研究系统、PDF、IDE 配置和 AI 编码工具目录。不要把 `.env`、`frontend/env-config.js`、`.runtime/`、本地模型、论文 PDF 或个人数据提交到仓库。

运行时主要生成文件：

- `.runtime/chapters.json`
- `.runtime/processes.json`
- `frontend/env-config.js`
- `backend/logs/`
- 本地 SQLite 数据库和缓存

## 文档

详细说明见 [docs/README.md](docs/README.md)。各模块 README 也保留在对应目录中，便于直接从代码目录了解职责。

## 许可证

本项目使用 MIT License。详见 [LICENSE](LICENSE)。
