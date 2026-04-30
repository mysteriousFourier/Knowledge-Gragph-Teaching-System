# Knowledge-Gragph-Teaching-System

基于知识图谱的交互式教学系统。项目提供教师端、学生端、知识图谱管理页和后端教育 API，核心目标是让授课文案、问答、练习题和反馈都尽量受知识图谱证据约束，而不是完全依赖大模型自由生成。

## 项目特点

- **教师端**：导入章节、生成授课文案、保存文稿、查看和维护知识图谱。
- **学生端**：学习章节内容、做题、点击选项答题、查看反馈、向系统提问。
- **知识图谱约束生成**：后端会先构建 `LearningPlan`，再约束大模型生成，最后返回一致性检查报告。
- **模型分流**：问答使用低延迟 `flash` 模型，授课文案和题库生成使用更适合深度生成的 `pro` 模型。
- **题库缓存**：首次生成题库后写入 `.runtime/chapters.json`，后续学生端优先读取缓存，避免每次重写练习题。
- **运行期配置**：端口、登录账号、DeepSeek API、模型名称均通过 `.env` 管理，避免把敏感信息写入源码。

## 技术栈

- 前端：静态 HTML、CSS、JavaScript
- 后端：Python、FastAPI、Uvicorn
- 数据与图谱：本地 JSON/SQLite/GraphML、向量检索、知识图谱服务
- AI：DeepSeek Chat Completions API
- 可视化：D3、vis-network、Cytoscape.js、KaTeX

## 目录结构

```text
.
├── app_config.py                  # 统一运行配置与环境变量加载
├── start.bat                      # Windows 一键启动
├── stop.ps1                       # 停止本地服务
├── .env.example                   # 环境变量模板
├── docs/                          # 面向开发者和维护者的模块文档
├── frontend/                      # 静态前端页面
│   ├── index.html                 # 首页
│   ├── teacher.html               # 教师端
│   ├── student.html               # 学生端
│   ├── workspace-ambient.*        # 黑色字符动效与液态玻璃 UI
│   └── graph-viewer.html          # 图谱查看页
├── backend/
│   ├── README.md                  # 后端模块入口文档
│   ├── start_all.py               # 后端服务编排启动器
│   ├── frontend_server.py         # 静态前端服务器
│   ├── education/                 # 教育 API 与 KG 约束生成
│   ├── maintenance/               # 维护与导入接口
│   ├── vector_index_system/       # 图谱/向量后端
│   └── mcp-server/                # MCP/图谱工具桥接
├── scripts/                       # 辅助脚本
├── structured/                    # 结构化教材章节、公式、表格
├── data/                          # 本地数据说明与忽略的数据库文件
├── THIRD_PARTY.md                 # 第三方依赖、仓库、论文和链接
└── LICENSE                        # MIT License
```

## 快速开始

### 1. 准备环境变量

复制 `.env.example` 为 `.env`，并按本机环境填写：

```env
PYTHON_EXE=
CONDA_ROOT=
CONDA_ENV_NAME=

APP_STUDENT_USERNAME=student
APP_STUDENT_PASSWORD=change-me
APP_TEACHER_USERNAME=teacher
APP_TEACHER_PASSWORD=change-me

DEEPSEEK_API_KEY=
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
DEEPSEEK_PRO_MODEL=deepseek-v4-pro
```

说明：

- `DEEPSEEK_FLASH_MODEL` 用于学生问答和教师端问答兜底。
- `DEEPSEEK_PRO_MODEL` 用于授课文案、自然补充和题库生成。
- `.env` 已被 `.gitignore` 忽略，不应提交到 Git。

### 2. 启动系统

Windows 下直接运行：

```bat
start.bat
```

启动后默认访问：

- 首页：<http://localhost:3000/>
- 学生端：<http://localhost:3000/student.html>
- 教师端：<http://localhost:3000/teacher.html>
- 教育 API：<http://127.0.0.1:8001/docs>
- 维护 API：<http://127.0.0.1:8002/docs>
- 后端图谱管理：<http://127.0.0.1:8080/admin>

### 3. 停止服务

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```

## 模块文档

更详细的模块说明集中在 `docs/`：

- [文档总览](docs/README.md)
- [运行配置与脚本](docs/modules/runtime-and-configuration.md)
- [后端启动编排](docs/modules/backend-orchestrator.md)
- [前端模块](docs/modules/frontend.md)
- [教育 API](docs/modules/education-api.md)
- [后台维护 API](docs/modules/maintenance-api.md)
- [图谱与向量模块](docs/modules/knowledge-graph-vector.md)
- [MCP 服务模块](docs/modules/mcp-server.md)
- [数据与资料模块](docs/modules/data-assets.md)
- [辅助脚本模块](docs/modules/scripts.md)

## 主要功能流程

### 教师端生成授课文案

1. 教师选择或导入章节。
2. 前端调用 `/api/education/generate-lecture`。
3. 后端读取知识图谱，构建 `LearningPlan`。
4. 使用 `DEEPSEEK_PRO_MODEL` 生成授课文案。
5. 返回文案、`learning_plan` 和 `consistency_report`。
6. 教师审核后保存文稿。

### 学生端问答

1. 学生输入问题。
2. 后端检索图谱和记忆上下文。
3. 使用 `DEEPSEEK_FLASH_MODEL` 快速生成回答。
4. 如果图谱证据不足，系统应明确提示“当前图谱依据不足”。

### 学生端练习题

1. 学生选择章节并加载练习。
2. 如果章节已有 `exercise_bank`，直接读取缓存。
3. 如果没有题库，后端基于知识图谱预创建题库。
4. 学生点击选项完成选择并提交。
5. 后端基于题目标准答案和图谱证据返回反馈。

## 知识图谱约束设计

```text
学习者输入
  -> Phase 1: Learning Planning
  -> Phase 2: Constrained Teaching / Interaction Generation
  -> Phase 3: Consistency & Pedagogy Checking
  -> 输出讲解 / 问题 / 反馈 + 知识依据 + 学习状态
```

核心实现位于：

- `backend/education/kg_constraints.py`
- `backend/education/api_server.py`
- `backend/education/claude_api.py`

关键返回字段：

- `learning_plan`：本轮允许使用的知识点、证据、关系和生成约束。
- `consistency_report`：知识支撑度、学习目标匹配、提示泄露风险等检查结果。

## 数据与缓存

- `.runtime/chapters.json`：运行期章节、授课文案、题库缓存。
- `.runtime/chapter_progress.json`：学生学习进度。
- `structured/`：结构化教材内容，适合提交到仓库。
- `backend/data/`：旧数据或本地生成数据，默认不提交。
- `frontend/env-config.js`：运行期前端配置，由后端生成，默认不提交。

注意：`.runtime/`、`.env`、数据库、日志、模型文件和虚拟环境都已被 `.gitignore` 忽略。

## 第三方与引用

项目使用外部仓库、源码、模型、论文、数据集或 CDN 库时，应单独列出链接、用途和许可证。这样做有三个原因：

1. 方便后续检查许可证和再分发条件。
2. 让读者知道哪些部分是本项目实现，哪些来自外部。
3. 公开到 GitHub 或其他平台时，可以减少版权和归属风险。

本项目将第三方信息集中放在 `THIRD_PARTY.md`。如果后续直接复制了某个仓库的代码，而不是只调用公开 API 或 CDN，需要把仓库链接、版本、许可证和改动说明补充进去。

## 开发检查

后端语法检查：

```powershell
python -m py_compile backend\education\api_server.py backend\education\claude_api.py backend\education\kg_constraints.py
```

前端脚本检查：

```powershell
node --check frontend\student.js
node --check frontend\teacher.js
```

## 常见问题

### 页面仍然加载旧效果

浏览器可能缓存了旧的 JS/CSS。项目前端资源已经带版本号，必要时强制刷新页面。

### 登录失败

确认 `.env` 中设置了：

```env
APP_STUDENT_PASSWORD=
APP_TEACHER_PASSWORD=
```

如果密码为空，后端会拒绝登录，避免默认弱密码进入源码。

### 题库每次都重新生成

检查 `.runtime/chapters.json` 是否可写。题库缓存写入失败时，页面仍会返回题目，但下次可能需要重新生成。

### DeepSeek 模型没有按任务分流

确认 `.env`：

```env
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
DEEPSEEK_PRO_MODEL=deepseek-v4-pro
```

重启后端后生效。

## 许可证

本项目采用 MIT License，详见 `LICENSE`。

第三方依赖、参考仓库、论文资料和 CDN 库的许可证与再分发说明集中记录在 `THIRD_PARTY.md`。公开发布或分发前，应确认其中列出的外部资源允许当前使用方式。
