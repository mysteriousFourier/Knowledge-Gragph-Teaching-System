# `backend/mcp-server/`

这个目录保留了旧的 `backend/mcp-server` 路径，主要用于兼容原有脚本、导入路径和工具约定。

当前 MCP 的主实现位于仓库根目录：

- `mcp_server/`

## 当前状态

- `backend/mcp-server/server.py` 是对根目录 `mcp_server.server` 的兼容导出
- `graph_manager.py` 等文件同样主要承担兼容职责
- 正常的单端口运行通常不会直接启动这里的服务

## 什么时候会用到这里

- 旧脚本仍然写死了 `backend/mcp-server/...` 路径
- 需要独立核对历史 MCP 目录结构
- 需要查看旧的独立依赖清单 `backend/mcp-server/requirements.txt`

## 当前推荐做法

- 新增或修改 MCP 工具时，直接修改根目录 `mcp_server/`
- 只有在兼容旧路径的 shim 本身需要调整时，才修改这个目录

## MCP 工具范围

当前 MCP / MCP 兼容层覆盖的能力包括：

- 读取整张图
- 查询节点、关系、图谱 schema
- 关键词搜索与语义搜索
- 新增/更新/删除节点与关系
- 子图、k-hop 邻居、前置知识、后续知识查询
- 批量导入图数据

## 备注

项目当前很多调用路径已经通过 `core/mcp_client.py` 和 `core/cli_dispatch.py` 在进程内完成兼容，不再要求单独拉起一个外部 MCP 进程。

在 Azure App Service 或 Azure for Students VM 上，也应保持这个进程内兼容模式。公网只暴露 `render_app.py` 提供的单端口 Web 服务，不单独开放 MCP 端口。
