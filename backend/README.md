# 后端总览

`backend/` 保存本项目的本地服务。前端本身是静态页面，后端负责统一启动、账号校验、课程生成、题库生成、知识图谱维护和图谱查询。

## 主要模块

```text
start_all.py                 启动编排器
frontend_server.py           静态前端服务器
education/                   教师端和学生端业务 API
maintenance/                 图谱维护 API
mcp-server/                  MCP 兼容图谱工具服务
vector_index_system/         图谱存储、搜索和后台管理页面
```

## 默认服务

| 服务 | 默认端口 | 职责 |
| --- | --- | --- |
| Frontend | 3000 | 提供静态页面并自动打开主页 |
| Education API | 8001 | 授课文案、题库、问答、章节缓存 |
| Maintenance API | 8002 | 图谱节点、关系、导入、同步、导出 |

端口和登录信息从 `.env` 读取。启动时会生成 `frontend/env-config.js`，让静态前端知道 API 地址。

## 运行方式

推荐在仓库根目录运行：

```bat
start.bat
```

停止服务：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_unlesspaper.ps1
```

## 文档

- [后端编排器](../docs/modules/backend-orchestrator.md)
- [教育 API](../docs/modules/education-api.md)
- [维护 API](../docs/modules/maintenance-api.md)
- [知识图谱与向量后端](../docs/modules/knowledge-graph-vector.md)
- [运行时与配置](../docs/modules/runtime-and-configuration.md)
