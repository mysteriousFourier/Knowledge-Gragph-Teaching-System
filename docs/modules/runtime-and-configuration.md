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

`start.bat` 会调用 `backend/start_all.py`。启动器会：

1. 读取 `.env`。
2. 解析 Python 解释器。
3. 生成 `frontend/env-config.js`。
4. 启动前端服务器。
5. 启动教育 API。
6. 启动维护 API。
7. 记录进程信息到 `.runtime/`。
8. 打开 `http://localhost:3000/`。

## 运行时文件

| 路径 | 说明 | 是否提交 |
| --- | --- | --- |
| `.runtime/chapters.json` | 章节缓存、授课文案、题库 | 否 |
| `.runtime/processes.json` | 当前服务进程记录 | 否 |
| `frontend/env-config.js` | 前端运行时 API 地址 | 否 |
| `backend/logs/` | 服务日志 | 否 |
| 本地数据库和索引 | 图谱、向量和缓存 | 否 |

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
