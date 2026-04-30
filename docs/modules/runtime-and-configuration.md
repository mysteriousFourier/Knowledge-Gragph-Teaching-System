# 运行配置与脚本

本模块覆盖项目的运行期配置、启动停止流程、端口约定和生成文件。核心文件位于根目录、`app_config.py`、`backend/start_all.py` 和 `stop.ps1`。

## 主要文件

| 路径 | 职责 |
| --- | --- |
| `.env.example` | 可提交的环境变量模板 |
| `.env` | 本机运行配置，包含密钥和密码，不提交 |
| `app_config.py` | 统一加载环境变量、构建服务地址、写入前端运行配置 |
| `start.bat` | Windows 一键启动入口 |
| `stop.ps1` | 停止本地服务和占用默认端口的进程 |
| `backend/start_all.py` | 编排启动教育 API、维护 API、图谱管理页和前端服务器 |
| `backend/frontend_server.py` | 静态前端服务器，关闭缓存便于本地调试 |

## 环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `PYTHON_EXE` | 空 | 明确指定 Python 解释器路径 |
| `CONDA_ROOT` | 空 | Conda 根目录，用于自动解析环境解释器 |
| `CONDA_ENV_NAME` | 空 | Conda 环境名 |
| `APP_SCHEME` | `http` | 构建服务访问地址的协议 |
| `APP_HOST` | `localhost` | 前端访问其他服务时使用的主机名 |
| `APP_BIND_HOST` | `0.0.0.0` | 后端服务监听地址 |
| `APP_LOOPBACK_HOST` | `127.0.0.1` | 本机端口检查和文档地址展示使用 |
| `FRONTEND_PORT` | `3000` | 静态前端服务端口 |
| `EDUCATION_API_PORT` | `8001` | 教育 API 端口 |
| `MAINTENANCE_API_PORT` | `8002` | 维护 API 端口 |
| `BACKEND_ADMIN_PORT` | `8080` | 图谱管理页端口 |
| `FRONTEND_BASE_URL` | 空 | 覆盖前端主地址 |
| `EDUCATION_API_BASE_URL` | 空 | 覆盖教育 API 地址 |
| `MAINTENANCE_API_BASE_URL` | 空 | 覆盖维护 API 地址 |
| `BACKEND_ADMIN_BASE_URL` | 空 | 覆盖图谱管理页地址 |
| `APP_STUDENT_USERNAME` | `student` | 学生账号 |
| `APP_STUDENT_PASSWORD` | 空 | 学生密码，空值会拒绝登录 |
| `APP_TEACHER_USERNAME` | `teacher` | 教师账号 |
| `APP_TEACHER_PASSWORD` | 空 | 教师密码，空值会拒绝登录 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek API key |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `DEEPSEEK_FLASH_MODEL` | `deepseek-v4-flash` | 问答等低延迟任务模型 |
| `DEEPSEEK_PRO_MODEL` | `deepseek-v4-pro` | 授课文案、自然补充、题库等深度生成任务模型 |
| `AUTO_OPEN_BROWSER` | `1` | 是否在启动完成后自动打开主界面 |

## 启动流程

1. `start.bat` 进入项目根目录并加载 `.env`。
2. 脚本按 `PYTHON_EXE`、`CONDA_ENV_PYTHON`、`CONDA_ROOT + CONDA_ENV_NAME`、本地虚拟环境、系统 Python 的顺序解析解释器。
3. `backend/start_all.py` 读取端口和基础 URL。
4. `app_config.py` 生成 `frontend/env-config.js`。
5. 后端生成 `frontend/chapters-cache.json`，供前端离线或首屏读取章节缓存。
6. 依次启动教育 API、维护 API、图谱管理页和前端服务器。
7. 进程信息写入 `.runtime/knowledge-gragph-teaching-system-processes.json`。
8. 如果 `AUTO_OPEN_BROWSER` 未关闭，自动打开 `http://localhost:3000/`。

## 停止流程

`stop.ps1` 会先读取 pid 文件并按 PID 停止服务；如果 pid 文件不存在或已失效，会检查默认端口并停止监听进程。默认检查端口来自 `.env` 或内置默认值。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```

用于自动化或脚本环境时，可加 `-NoPause`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1 -NoPause
```

## 运行期生成文件

| 路径 | 来源 | 是否提交 |
| --- | --- | --- |
| `.runtime/` | 启动器、前端预览、缓存、截图、日志 | 否 |
| `.runtime/logs/*.log` | `backend/start_all.py` 启动的子进程日志 | 否 |
| `frontend/env-config.js` | `app_config.py` | 否 |
| `frontend/chapters-cache.json` | `backend/start_all.py` | 否 |
| `backend/data/chapters.json` | 教育 API 保存章节、文案、题库 | 视数据来源决定，默认不提交 |
| `backend/data/teacher_memory_package.json` | 维护 API 导出的教师端图谱包 | 视数据来源决定，默认不提交 |

## 配置变更规则

- 新增面向运行环境的配置项时，必须同时更新 `.env.example`、`app_config.py` 和本文档。
- 真实 API key、账号密码、本机绝对路径不得写入 README、示例截图或源码。
- 新增服务端口时，需要同步更新 `stop.ps1` 的端口清理逻辑。
- 前端需要读取的新服务地址，应通过 `window.__APP_CONFIG__` 注入，不直接在页面内写死生产地址。
