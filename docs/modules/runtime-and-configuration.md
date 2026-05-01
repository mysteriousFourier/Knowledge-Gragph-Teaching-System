# 运行时与配置

本项目通过 `.env` 配置本地运行环境。`.env` 只保存在本机，不提交到 Git；公开仓库只保留 `.env.example`。

## 关键配置

| 配置项 | 用途 |
| --- | --- |
| `APP_STUDENT_USERNAME` / `APP_STUDENT_PASSWORD` | 学生端登录 |
| `APP_TEACHER_USERNAME` / `APP_TEACHER_PASSWORD` | 教师端登录 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `DEEPSEEK_FLASH_MODEL` | 问答使用的快速模型 |
| `DEEPSEEK_PRO_MODEL` | 文案和题库使用的深度模型 |
| `DEEPSEEK_GENERATION_READ_TIMEOUT_SECONDS` | 深度生成任务读取超时；`0` 表示不中途取消 |
| `APP_HOST` | 本地页面和 API 地址使用的主机名，默认 `127.0.0.1` |
| `APP_BIND_HOST` | 服务监听地址，默认 `0.0.0.0` |
| `APP_LOOPBACK_HOST` | 启动器检测端口和打印地址时使用的回环地址 |
| `APP_RUNTIME_DIR` | 运行时缓存目录，默认 `.runtime/` |
| `APP_DATA_DIR` | 单端口部署时的数据目录 |
| `GRAPH_DB_PATH` | 图谱 SQLite 数据库路径 |
| `FRONTEND_PORT` | 前端端口，默认 3000 |
| `EDUCATION_API_PORT` | 教育 API 端口，默认 8001 |
| `MAINTENANCE_API_PORT` | 维护 API 端口，默认 8002 |
| `PYTHON_EXE` / `CONDA_ENV_PYTHON` | 指定 Python 解释器 |

默认模型名示例：

```env
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
DEEPSEEK_PRO_MODEL=deepseek-v4-pro
```

## 启动流程

### 多端口本地开发

`start.bat` 会调用 `backend/start_all.py`。启动器会：

1. 读取 `.env`。
2. 解析 Python 解释器。
3. 生成 `frontend/env-config.js`。
4. 启动前端服务器。
5. 启动教育 API。
6. 启动维护 API。
7. 记录进程信息到 `.runtime/`。
8. 打开 `http://127.0.0.1:3000/`。

### 单端口部署验证

`start_render_local.bat` 会调用 `render_app.py`，在一个 FastAPI 服务中提供前端页面、教育 API、维护 API 和图谱后台。默认地址仍是：

```text
http://127.0.0.1:3000/
```

单端口模式不会写入 `frontend/env-config.js`；`/env-config.js` 由 FastAPI 动态返回，并把 API 地址指向当前页面同源地址。

更多说明见 [单端口 FastAPI 版本](single-port-fastapi.md)。

## 运行时文件

| 路径 | 说明 | 是否提交 |
| --- | --- | --- |
| `.runtime/chapters.json` | 章节缓存、授课文案、题库 | 否 |
| `.runtime/processes.json` | 当前服务进程记录 | 否 |
| `frontend/env-config.js` | 前端运行时 API 地址 | 否 |
| `backend/logs/` | 服务日志 | 否 |
| 本地数据库和索引 | 图谱、向量和缓存 | 否 |

单端口部署到 Render 且需要长期保留题库反馈、批准题库和图谱数据库时，应使用 Persistent Disk，并把 `APP_RUNTIME_DIR`、`APP_DATA_DIR`、`GRAPH_DB_PATH` 指向磁盘挂载目录。

## 停止服务

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_unlesspaper.ps1
```

停止脚本会优先使用 `.runtime/processes.json`，同时检查默认端口，避免只关闭窗口而留下后端进程。

## 安全规则

- 不提交 `.env`、`frontend/env-config.js`、`.runtime/`、日志、数据库和模型。
- 不把 API Key 写进前端代码。
- 不在公开文档中写个人绝对路径。
- 若新增运行时文件，先更新 `.gitignore`。
- 改名根目录前先停止服务；若 `.env` 中写过绝对路径，改名后需要同步修改。
