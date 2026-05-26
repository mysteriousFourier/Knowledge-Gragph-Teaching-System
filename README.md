# KGTS

知识图谱教学系统（KGTS）是一个面向教学场景的知识图谱应用仓库，包含 React + Vite 前端、Python API 服务、课程结构化数据、知识图谱维护工具，以及图谱管理页面。

当前推荐的运行方式是根目录的单端口模式：React 构建产物、教学 API、维护 API 和图谱管理页统一由 `render_app.py` 托管，便于本地测试和部署，实际并不使用render免费版的全栈部署，因为需要信用卡进行验证。

> [演示站点浏览，可进行知识图谱体验](http://kgts.southeastasia.cloudapp.azure.com)

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
scripts/launchers/            其他启动脚本和实验脚本
requirements/                 可选依赖清单：向量检索、TTS 等
```

`education/`、`maintenance/`、`mcp_server/`、`core/` 是当前主实现；`backend/` 主要保留兼容入口和仍在运行时使用的旧目录资产。

## 快速开始

### 方式一：Windows 一键启动

在仓库根目录运行：

```powershell
.\scripts\launchers\start.ps1
```

或：

```bat
scripts\launchers\start.bat
```

脚本会自动检查 Python 依赖、前端构建产物，并在需要时执行安装与构建。
其他实验启动脚本位于 `scripts/launchers/`，避免根目录继续膨胀。

`start.bat` 默认打开 `http://127.0.0.1:8000/`。如果需要本地 HTTPS，把证书放到：

```text
.runtime/certs/localhost.pem
.runtime/certs/localhost-key.pem
```

再次运行 `scripts\launchers\start.bat` 时会自动改用 `https://127.0.0.1:8000/`。本地开发建议用 `mkcert` 生成受信任证书；Azure 公网部署仍建议由 Nginx + Certbot 或 Azure 平台证书终止 HTTPS，再反代到本机服务。

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

## Azure App Service 部署

当前 `main` 分支包含 GitHub Actions 工作流：

```text
.github/workflows/azure-main-kgts-interactive-learning-system.yml
```

该工作流会先构建 React 前端，再把单端口 Python 应用部署到 Azure App Service。

Azure App Service 的 Startup Command 建议设置为：

```bash
bash startup.sh
```

如果 Portal 不接受脚本，也可以设置为：

```bash
python -m uvicorn render_app:app --host 0.0.0.0 --port $PORT
```

Azure 冷启动健康探测时间有限，默认会跳过结构化图谱重建和图谱清理这类启动维护任务，避免出现 `ContainerTimeout`。相关环境变量：

- `APP_RUN_STARTUP_MAINTENANCE=0`
- `RENDER_AUTO_SYNC_STRUCTURED=0`
- `APP_BOOTSTRAP_SEED_DATA=1`
- `DEEPSEEK_GENERATION_READ_TIMEOUT_SECONDS=0`

### 本地 GraphRAG 检索配置

本地默认使用真正的 `hybrid` GraphRAG：图谱节点 embedding + FAISS 向量索引召回，再用图关系补充公式、例题、表格和前后置节点。先安装可选向量依赖：

```bash
python -m pip install -r requirements/vector.txt
```

在低内存 Linux VM 上不要直接让 PyPI 解析 torch，否则可能拉取 CUDA 版依赖。改用 CPU-only 文件：

```bash
python -m pip install -r requirements/vector-cpu.txt
```

默认环境变量：

```text
KGTS_RETRIEVAL_MODE=hybrid
KGTS_VECTOR_INDEX_DIR=.runtime/vector_index
KGTS_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
KGTS_EMBEDDING_LOCAL_FILES_ONLY=1
KGTS_VECTOR_STARTUP_ENSURE=0
```

如果本机没有缓存该 embedding 模型，先下载/放置模型，或把 `KGTS_EMBEDDING_MODEL` 改为本地模型目录。缺失时接口会在 `vector_stats.last_error` 中给出明确错误，不会静默降级为 `graph_db`。`KGTS_VECTOR_STARTUP_ENSURE=0` 会避免 Web 服务启动时预热 embedding；第一次混合检索或手动重建索引时再加载模型。

### Azure F1 检索配置

Azure F1 部署保持 `hybrid` 神经向量检索能力，但按低内存方式运行：安装 CPU-only 向量依赖，不在启动时预热 embedding，查询或重建后释放模型引用。生产默认：

```text
KGTS_RETRIEVAL_MODE=hybrid
KGTS_VECTOR_STARTUP_ENSURE=0
KGTS_VECTOR_UNLOAD_AFTER_QUERY=1
KGTS_VECTOR_UNLOAD_AFTER_REBUILD=1
KGTS_VECTOR_HASH_FALLBACK=1
```

GitHub Actions 会安装 `requirements/vector-cpu.txt`，并继续排除 `backend/vector_index_system/models/`、`backend/vector_index_system/vector_index/` 和大模型权重，避免部署包膨胀。若线上没有可用 embedding 缓存，系统会保留 hybrid 接口并使用 hashing fallback，不会把功能关掉。

### 可选本地语音推理

项目预留了 `/api/tts/*` 接口，本地可用 `genie` provider 加载项目内模型。Azure F1 主站不直接加载本地 TTS 权重，但 TTS 功能保持启用，通过 server provider 调用独立推理服务：

```text
KGTS_TTS_ENABLED=1
KGTS_TTS_PROVIDER=genie_server
KGTS_TTS_SERVER_URL=http://127.0.0.1:9880
```

部署包会排除 TTS 模型、缓存和生成音频。线上语音需要把 Genie/GPT-SoVITS 放在独立进程、独立 VM 或外部推理服务里，再把 `KGTS_TTS_SERVER_URL` 指向该服务。本地启用方式见 [本地语音推理](docs/tts-genie.md)。

## Azure for Students VM 部署

如果要部署到 Azure for Students 免费 VM，优先选择 `Standard_B2ats_v2`；它是 AMD x86-64、2 vCPU / 1 GB RAM，在当前免费 VM 候选里比 `Standard_B1s` 更适合 KGTS，同时比 Arm 规格更少依赖兼容风险。若目标地区没有该 SKU 或订阅无配额，再退回 `Standard_B1s`。

免费 VM 线上配置必须保持功能开启但低内存：

```text
KGTS_RETRIEVAL_MODE=hybrid
KGTS_VECTOR_STARTUP_ENSURE=0
KGTS_VECTOR_UNLOAD_AFTER_QUERY=1
KGTS_VECTOR_UNLOAD_AFTER_REBUILD=1
KGTS_VECTOR_HASH_FALLBACK=1
KGTS_TTS_ENABLED=1
KGTS_TTS_PROVIDER=genie_server
KGTS_TTS_SERVER_URL=http://127.0.0.1:9880
APP_RUN_STARTUP_MAINTENANCE=0
RENDER_AUTO_SYNC_STRUCTURED=0
APP_BOOTSTRAP_SEED_DATA=1
```

如果需要在同一台 1 GB VM 上实验本地 Genie-TTS 和神经向量检索，按错峰运行处理：TTS 只用于朗读课件，向量检索只用于备课/问答；不要让两者同时常驻。向量依赖使用 `requirements/vector-cpu.txt`，并开启：

```text
KGTS_RETRIEVAL_MODE=hybrid
KGTS_VECTOR_STARTUP_ENSURE=0
KGTS_VECTOR_UNLOAD_AFTER_QUERY=1
KGTS_VECTOR_UNLOAD_AFTER_REBUILD=1
```

完整 VM 创建、systemd 和 Nginx 部署步骤见 [Azure for Students VM 部署](docs/azure-student-vm.md)。

## 文档索引

- [前端说明](frontend/README.md)
- [后端兼容目录说明](backend/README.md)
- [检索模式与 Azure F1 说明](docs/retrieval-modes.md)
- [本地语音推理](docs/tts-genie.md)
- [Azure for Students VM 部署](docs/azure-student-vm.md)
- [数据目录说明](data/README.md)
- [结构化数据说明](structured/README.md)
- [第三方依赖迁移说明](docs/THIRD_PARTY_MIGRATION.md)

## 运行截图演示

<img width="2560" height="1380" alt="index" src="https://github.com/user-attachments/assets/8510a239-e652-4d5c-82f5-c6747c794582" />
主界面

<img width="2560" height="1380" alt="exam" src="https://github.com/user-attachments/assets/a20caa87-a2a2-4443-ba2c-0b708a32e5c7" />
测试题

<img width="2560" height="1380" alt="teacher" src="https://github.com/user-attachments/assets/46caec53-9947-43d5-8d83-4628b77623f4" />
教师端

<img width="2560" height="1380" alt="sheet" src="https://github.com/user-attachments/assets/03b812c7-3454-4b84-bc3d-f729ab52c2ca" />
授课文案

<img width="2560" height="1380" alt="graph-1" src="https://github.com/user-attachments/assets/ed9d5a25-d48c-4ad2-a101-2372676fa7e0" />
图谱示例1

<img width="2560" height="1380" alt="graph" src="https://github.com/user-attachments/assets/1f0b0f8f-b4da-47e4-9426-5fcec46a3006" />
图谱示例2

<img width="2560" height="1380" alt="graph-admin" src="https://github.com/user-attachments/assets/90f39d5d-7309-4c9d-8da1-c15791810680" />
图谱管理，仅教师端，教师端也可直接编辑图谱








