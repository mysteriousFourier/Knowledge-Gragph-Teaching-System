# KGTS

Knowledge Graph Teaching System（KGTS）是一个面向教学场景的知识图谱应用仓库，包含 React + Vite 前端、Python API 服务、课程结构化数据、知识图谱维护工具，以及图谱管理页面。

当前推荐的运行方式是根目录的单端口模式：React 构建产物、教学 API、维护 API 和图谱管理页统一由 `render_app.py` 托管，便于本地测试和部署。

## 当前实现状态

- 前端是 React + Vite，源码位于 `frontend/`
- 后端 API 由 Python 服务提供，单端口入口是 `render_app.py`
- 教师端每次点击“生成新题”生成 5 道新题，题库总量不设置上限
- 学生练习每次随机抽取最多 10 题，并排除教师点踩的题目
- 题目选项支持 Markdown / LaTeX 渲染，并会去除重复的 `A. A.` 选项前缀
- 页面已补充移动端适配，手机端优先显示实际工作区，图谱和导航会收敛为窄屏布局

## 功能概览

- 教师端：备课、讲稿生成、PPT 解析、练习题生成
- 学生端：学习、练习、复习、问答
- 图谱维护：节点/关系编辑、导入导出、结构化数据同步
- 图谱浏览：图谱主页与后台管理页

## 仓库结构

```text
frontend/                     React + Vite 前端
education/                    教学域主逻辑
maintenance/                  图谱维护域主逻辑
mcp_server/                   MCP 工具定义与服务实现
core/                         图谱、桥接、运行时核心逻辑
models/                       Pydantic / 类型模型
backend/                      兼容旧目录结构的启动器、shim 和图谱后台资产
structured/                   可公开提交的结构化课程数据
data/seed/                    可提交的启动种子数据
render_app.py                 当前推荐的单端口入口
start.bat / start.ps1         Windows 一键启动脚本
```

`education/`、`maintenance/`、`mcp_server/`、`core/` 是当前主实现；`backend/` 主要保留兼容入口和仍在运行时使用的旧目录资产。

## 快速开始

### 方式一：Windows 一键启动

在仓库根目录运行：

```powershell
.\start.ps1
```

或：

```bat
start.bat
```

脚本会自动检查 Python 依赖、前端构建产物，并在需要时执行安装与构建。

### 方式二：手动启动

1. 安装后端依赖

```bash
python -m pip install -r requirements.txt
```

2. 安装并构建前端

```bash
cd frontend
npm install
npm run build
cd ..
```

3. 启动单端口服务

```bash
python render_app.py
```

默认访问地址：

- 应用主页：`http://127.0.0.1:8000/`
- 图谱后台：`http://127.0.0.1:8000/admin`
- API 文档：`http://127.0.0.1:8000/docs`

调试接口问题时建议在前台运行 `python render_app.py`，让终端直接显示后端日志。不要用静默后台方式启动长期服务，否则生成题目、图谱导入等错误不容易定位。

## 开发模式

前端开发服务器：

```bash
cd frontend
npm run dev
```

默认会把 `/api` 和 `/env-config.js` 代理到 `http://127.0.0.1:8000`。如需改到其他后端地址，设置：

```bash
VITE_DEV_API_TARGET=http://127.0.0.1:8000
```

后端仍建议在仓库根目录启动：

```bash
python render_app.py
```

## 配置与数据目录

- `.env.example`：示例配置
- `.runtime/`：运行时生成的章节、日志和缓存
- `structured/`：可公开提交的课程结构化数据
- `data/seed/`：可提交的启动种子数据
- `backend/vector_index_system/knowledge_graph/`：默认本地图谱数据库位置

常见环境变量：

- `APP_RUNTIME_DIR`：运行时章节与日志目录
- `APP_DATA_DIR`：运行时数据目录
- `GRAPH_DB_PATH`：显式指定图谱数据库路径
- `APP_BOOTSTRAP_SEED_DATA`：是否启用种子数据引导
- `DEEPSEEK_API_KEY`：教学生成与问答能力所需 API Key

## 兼容模式

如果需要保留旧的多服务拆分方式，可以使用：

```bash
python backend/start_all.py
```

该模式会分别启动前端静态服务、教育 API、维护 API 和图谱后台页，但日常开发与部署优先使用根目录单端口模式。

## 文档索引

- [前端说明](frontend/README.md)
- [后端兼容目录说明](backend/README.md)
- [数据目录说明](data/README.md)
- [结构化数据说明](structured/README.md)
- [第三方依赖迁移说明](THIRD_PARTY_MIGRATION.md)
