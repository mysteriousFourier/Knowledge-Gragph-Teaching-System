# Knowledge-Gragph-Teaching-System Documentation

本目录提供面向开发者、审阅者和后续维护者的项目文档。根目录 `README.md` 负责快速介绍和启动说明；本目录负责解释模块边界、数据流、运行配置和扩展点。

## 文档索引

| 文档 | 覆盖范围 |
| --- | --- |
| [运行配置与脚本](modules/runtime-and-configuration.md) | `.env`、端口、启动停止、运行期生成文件 |
| [后端启动编排](modules/backend-orchestrator.md) | `backend/start_all.py`、前端静态服务器、日志和进程管理 |
| [前端模块](modules/frontend.md) | 首页、教师端、学生端、图谱页面、动效与 API 配置 |
| [教育 API](modules/education-api.md) | 授课文案、问答、题库、学生学习流程、KG 约束 |
| [后台维护 API](modules/maintenance-api.md) | 图谱导入、节点关系维护、结构化数据同步、导出与校验 |
| [图谱与向量模块](modules/knowledge-graph-vector.md) | `GraphService`、SQLite/GraphML、向量检索、记忆 provider 编排 |
| [MCP 服务模块](modules/mcp-server.md) | MCP 工具桥接、图谱工具接口、与主图谱模块的关系 |
| [数据与资料模块](modules/data-assets.md) | `structured/`、运行期缓存、本地数据库、论文和第三方资料 |
| [辅助脚本模块](modules/scripts.md) | `scripts/`、`start.bat`、`stop.ps1`、脚本扩展规范 |

## 模块边界

项目按运行职责划分为四层：

1. 前端层：`frontend/` 提供纯静态 HTML、CSS、JavaScript 页面。
2. 教育服务层：`backend/education/` 面向教师端和学生端业务流程。
3. 维护服务层：`backend/maintenance/` 面向知识图谱管理、导入、校验和导出。
4. 图谱与检索层：`backend/vector_index_system/` 提供节点、关系、向量检索和记忆 provider 编排。

`backend/start_all.py` 负责把以上服务组合成一个本地运行系统，并为前端写入运行期配置。

## 关键入口

| 入口 | 默认地址或命令 | 说明 |
| --- | --- | --- |
| 主界面 | `http://localhost:3000/` | 首页，进入教师端、学生端和图谱管理 |
| 学生端 | `http://localhost:3000/student.html` | 学习章节、练习题、问答 |
| 教师端 | `http://localhost:3000/teacher.html` | 生成授课文案、维护图谱、补充内容 |
| 教育 API | `http://127.0.0.1:8001/docs` | 学生端和教师端业务 API |
| 维护 API | `http://127.0.0.1:8002/docs` | 图谱维护 API |
| 图谱管理页 | `http://127.0.0.1:8080/admin` | 后端图谱管理界面 |
| 启动 | `start.bat` | Windows 一键启动 |
| 停止 | `powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1` | 停止本地服务和默认端口进程 |

## 维护原则

- 公共运行参数放入 `.env` 或 `.env.example`，不在源码中硬编码真实密钥和本机路径。
- 新增 API 时同步更新对应模块文档，并保证 FastAPI `/docs` 可解释请求和响应。
- 新增前端页面时同步更新 `frontend/README.md` 和 [前端模块](modules/frontend.md)。
- 新增外部仓库、论文、模型、数据集或 CDN 资源时同步更新 `THIRD_PARTY.md`。
- 运行期缓存、数据库、日志、浏览器临时目录和本地模型不应提交到 Git。
