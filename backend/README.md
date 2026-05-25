# `backend/`

`backend/` 主要保存兼容旧目录结构的启动器、shim 和仍在运行时使用的图谱后台资产。它不是仓库里唯一的后端实现来源，也不是 React 前端目录。

当前主逻辑位于仓库根目录的：

- `education/`
- `maintenance/`
- `mcp_server/`
- `core/`

## 这个目录里有什么

| 路径 | 作用 |
| --- | --- |
| `education/` | 教学 API 的兼容入口，实际路由逻辑在根目录 `education/` |
| `maintenance/` | 维护 API 的兼容入口，实际路由逻辑在根目录 `maintenance/` |
| `mcp-server/` | 保留旧路径的 MCP 兼容目录，主实现见根目录 `mcp_server/` |
| `vector_index_system/` | 图谱后台页、图谱数据库、旧图谱/向量子系统资产 |
| `start_all.py` | 旧的多服务拆分启动器 |
| `frontend_server.py` | 旧模式下的静态前端服务 |

## 推荐运行方式

日常开发和部署优先从仓库根目录启动：

```bash
python render_app.py
```

或使用 Windows 启动脚本：

```powershell
.\start.ps1
```

需要排查 API 报错时，优先在前台运行上述命令，让日志直接输出到当前终端。不要把长期服务静默放到后台，否则题目生成、图谱上传等问题难以及时看到 traceback。

Linux VM 或 App Service 上推荐直接运行：

```bash
python -m uvicorn render_app:app --host 0.0.0.0 --port ${PORT:-8000}
```

VM 上可用 systemd 管理这个命令，再用 Nginx 把 80 端口转发到本机 8000。完整步骤见 [Azure for Students VM 部署](../docs/azure-student-vm.md)。

## 何时使用这个目录下的脚本

如果你明确要跑旧的多服务模式，可以使用：

```bash
python backend/start_all.py
```

该模式会分别启动：

- 前端静态服务
- 教学 API
- 维护 API
- 图谱后台管理页

## 维护约定

- 需要改业务逻辑时，优先改根目录 `education/`、`maintenance/`、`mcp_server/`、`core/`
- 只有在兼容入口、旧脚本或后台资产本身需要调整时，才改 `backend/`
- `backend/data/`、日志、缓存和本地数据库不应作为长期版本化数据来源

## 子目录文档

- [教学 API 兼容入口](education/README.md)
- [维护 API 兼容入口](maintenance/README.md)
- [MCP 兼容目录](mcp-server/README.md)
- [图谱与向量子系统](vector_index_system/README.md)
