# 单端口 FastAPI 版本

本项目同时保留两种本地运行方式：

- `start.bat`：本地开发用，多进程、多端口，前端在 `3000`，教育 API 在 `8001`，维护 API 在 `8002`，图谱后台在 `8080`。
- `start_render_local.bat` / `render_app.py`：部署验证用，单个 FastAPI Web Service 对外只暴露一个端口，默认 `3000`。

当前准备推送的新分支以单端口版本为主。它更接近 Render 的运行环境，也更容易部署、演示和回滚。

## 入口文件

单端口版本入口是仓库根目录的 `render_app.py`。它负责：

- 挂载 `frontend/` 静态页面。
- 动态返回 `/env-config.js`，让前端 API 地址指向当前域名。
- 合并教育 API 路由和维护 API 路由。
- 提供 `/admin` 图谱后台入口。
- 提供 `/api/health` 健康检查。
- 在图谱节点过少时，从 `structured/` 自动同步结构化图谱数据。
- 对主页 `/` 和 `/index.html` 返回 no-store 响应，避免浏览器缓存旧主页资源。

## 常用地址

本地单端口验证：

```text
http://127.0.0.1:3000/
http://127.0.0.1:3000/teacher.html
http://127.0.0.1:3000/student.html
http://127.0.0.1:3000/admin
http://127.0.0.1:3000/api/health
```

Render 上线后路径保持一致，只是域名换成 Render 分配的域名。

## 本地启动

推荐直接运行：

```bat
start_render_local.bat
```

指定端口：

```bat
start_render_local.bat 3100
```

手动命令：

```powershell
uv run --with fastapi --with "uvicorn[standard]" --with pydantic --with python-dotenv --with httpx uvicorn render_app:app --host 127.0.0.1 --port 3000
```

## Render 配置

仓库提供 `render.yaml`。Render Web Service 的关键配置是：

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn render_app:app --host 0.0.0.0 --port $PORT
Health Check Path: /api/health
```

必须配置的环境变量：

```text
DEEPSEEK_API_KEY
APP_STUDENT_PASSWORD
APP_TEACHER_PASSWORD
```

推荐保留的模型配置：

```text
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
DEEPSEEK_PRO_MODEL=deepseek-v4-pro
DEEPSEEK_GENERATION_READ_TIMEOUT_SECONDS=0
```

`flash` 用于学生端和教师端问答；`pro` 用于授课文案、题库和选项重写等深度生成任务。

## 数据持久化

单端口服务默认仍会写运行时数据：

```text
.runtime/chapters.json
.runtime/processes.json
.runtime/logs/
```

Render 普通 Web Service 文件系统不适合长期保存这些数据。需要长期保留题库反馈、批准题库和图谱数据库时，应挂载 Persistent Disk，并设置：

```text
APP_RUNTIME_DIR=/var/data/runtime
APP_DATA_DIR=/var/data/app-data
GRAPH_DB_PATH=/var/data/knowledge_graph.db
```

## 图谱自动同步

`render_app.py` 启动时会检查图谱节点数量。若节点数低于阈值，会从 `structured/` 同步公开结构化数据，避免部署后图谱后台只有一个节点。

可配置项：

```text
RENDER_AUTO_SYNC_STRUCTURED=1
RENDER_AUTO_SYNC_MIN_NODES=20
```

关闭自动同步：

```text
RENDER_AUTO_SYNC_STRUCTURED=0
```

## 前端资源和缓存

主页 `index.html` 只加载本地 `home.css` 和 `home.js`，不再等待外部 CDN。这样主入口字符背景和滚动上浮动效不会被网络请求阻塞。

教师端、学生端和图谱页仍按各自页面需要加载 Markdown、LaTeX 和图谱可视化资源。修改前端脚本后应递增查询参数版本号，例如：

```html
<script src="teacher.js?v=38"></script>
```

如果页面表现不符合预期，先检查浏览器实际加载的版本号，再硬刷新。

## 与多端口版本的差异

| 项目 | 多端口开发模式 | 单端口 FastAPI 模式 |
| --- | --- | --- |
| 启动入口 | `start.bat` | `start_render_local.bat` 或 `render_app.py` |
| 端口 | `3000`、`8001`、`8002`、`8080` | 一个公开端口，默认 `3000` |
| `/env-config.js` | 由启动器写入 `frontend/env-config.js` | 由 FastAPI 动态返回 |
| API 访问 | 前端跨端口访问 API | 前端同源访问 API |
| 部署匹配度 | 适合本地调试 | 适合 Render 和演示 |

## 验证清单

提交或部署前至少检查：

- `http://127.0.0.1:3000/` 主入口可打开，背景字符和滚动上浮动效存在。
- 教师端可登录、生成授课文案、继续生成题库、评价题目和选项。
- 学生端可登录、加载课程内容、加载练习题、点击选项作答。
- 教师端和学生端问答可用，Markdown 与 LaTeX 同时渲染。
- `/admin` 可打开图谱后台，右侧详情可渲染文本和公式。
- `/api/health` 返回健康状态。
- `.env`、`frontend/env-config.js`、`.runtime/`、数据库、日志和模型文件没有进入 Git。
