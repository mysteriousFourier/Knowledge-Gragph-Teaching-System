# Backend Module

`backend/` 包含本项目的服务端代码，包括启动编排、教育 API、后台维护 API、图谱与向量模块，以及 MCP 工具桥接。

## 子模块

| 路径 | 说明 | 文档 |
| --- | --- | --- |
| `start_all.py` | 本地服务启动编排 | [后端启动编排](../docs/modules/backend-orchestrator.md) |
| `frontend_server.py` | 静态前端服务器 | [后端启动编排](../docs/modules/backend-orchestrator.md) |
| `education/` | 教师端和学生端业务 API | [教育 API](../docs/modules/education-api.md) |
| `maintenance/` | 图谱维护、导入、导出和校验 API | [后台维护 API](../docs/modules/maintenance-api.md) |
| `vector_index_system/` | 图谱、向量、记忆 provider 和管理页 | [图谱与向量模块](../docs/modules/knowledge-graph-vector.md) |
| `mcp-server/` | MCP 工具桥接 | [MCP 服务模块](../docs/modules/mcp-server.md) |

## 启动

后端通常不单独启动，推荐从根目录运行：

```bat
start.bat
```

调试单个服务时，可直接运行对应 `api_server.py`，但需要先配置 `.env`。
