# 后端启动编排模块

后端启动编排模块负责把多个独立服务组合成本地可运行系统。主要入口是 `backend/start_all.py`，配套静态服务器为 `backend/frontend_server.py`。

## 职责

- 解析 Python 运行环境。
- 校验服务端口是否空闲。
- 写入前端运行配置和章节缓存。
- 启动教育 API、维护 API、图谱管理页和前端静态服务。
- 记录子进程 PID 和日志位置。
- 在控制台中展示访问地址。
- 启动完成后自动打开主界面。

## 启动的服务

| 进程名 | 入口 | 默认端口 | 说明 |
| --- | --- | --- | --- |
| `education` | `backend/education/api_server.py` | `8001` | 教师端和学生端业务 API |
| `maintenance` | `backend/maintenance/api_server.py` | `8002` | 图谱维护、结构化同步、导入导出 API |
| `backend-admin` | `backend/vector_index_system/backend_admin.py` | `8080` | 后端图谱管理页面 |
| `frontend` | `backend/frontend_server.py` | `3000` | 静态前端文件服务 |

## 文件输出

| 文件 | 内容 |
| --- | --- |
| `.runtime/knowledge-gragph-teaching-system-processes.json` | 当前服务进程 PID 和端口 |
| `.runtime/logs/education.out.log` | 教育 API 标准输出 |
| `.runtime/logs/education.err.log` | 教育 API 错误输出 |
| `.runtime/logs/maintenance.out.log` | 维护 API 标准输出 |
| `.runtime/logs/maintenance.err.log` | 维护 API 错误输出 |
| `.runtime/logs/backend-admin.*.log` | 图谱管理页日志 |
| `.runtime/logs/frontend.*.log` | 前端服务器日志 |

## 端口冲突处理

启动器在创建进程前会检查端口是否已被占用。如果端口冲突，启动流程会停止并提示运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```

如果端口由其他程序占用，应先确认该程序是否属于本项目。`stop.ps1` 会停止默认端口监听进程，适合本地开发环境；共享机器或生产环境应手动确认进程来源。

## 前端运行配置注入

启动器调用 `app_config.write_frontend_runtime_config()` 写入 `frontend/env-config.js`。前端通过 `window.__APP_CONFIG__` 读取服务地址，例如：

```javascript
const APP_CONFIG = window.__APP_CONFIG__ || {};
```

该文件属于运行期产物，已被 `.gitignore` 忽略。

## 扩展新服务

新增后端服务时，需要完成以下修改：

1. 在 `.env.example` 中添加端口或基础 URL。
2. 在 `app_config.py` 中添加默认端口和前端配置字段。
3. 在 `backend/start_all.py` 中添加端口读取、启动函数和 `ports` 记录。
4. 在 `stop.ps1` 中把新端口加入停止范围。
5. 在 `docs/modules/runtime-and-configuration.md` 和本文档中记录新服务。
