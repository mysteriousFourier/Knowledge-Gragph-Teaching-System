# MCP 服务模块

MCP 服务模块位于 `backend/mcp-server/`，用于把知识图谱能力暴露为 MCP 工具。当前项目的主业务路径主要通过教育 API、维护 API 和 `backend/vector_index_system/` 完成；MCP 模块保留为工具桥接和兼容层。

## 主要文件

| 文件 | 职责 |
| --- | --- |
| `server.py` | MCP 工具入口和参数模型 |
| `graph_manager.py` | MCP 模块内部图谱管理 |
| `storage.py` | 节点、关系和存储抽象 |
| `vector_index.py` | MCP 模块内的向量索引 |
| `graphml_importer.py` | GraphML 解析和格式转换 |
| `config.py` | MCP 服务配置 |
| `mcp_config_example.py` | 客户端配置示例 |
| `data/` | MCP 模块本地数据目录，默认不提交数据库 |

## 工具能力

MCP 工具覆盖以下类别：

| 类别 | 工具 |
| --- | --- |
| 图谱读取 | `read_graph`, `get_node`, `get_relations`, `get_graph_schema` |
| 搜索 | `search_nodes`, `semantic_search` |
| 图谱更新 | `add_memory`, `update_memory`, `delete_memory`, `add_relation` |
| 路径和邻居 | `get_neighbors`, `trace_call_path`, `get_k_hop_neighbors`, `get_prerequisites`, `get_follow_up` |
| 导入 | `batch_import_graph`, `import_graphml` |
| 统计 | `get_graph_statistics`, `get_subgraph_by_type` |
| 教育辅助 | `get_note`, `discover_weak_relations` |

## 与主图谱模块的关系

`backend/vector_index_system/cli.py` 已提供一组兼容工具分发能力，教育 API 和维护 API 也直接调用 `GraphService`。因此 MCP 模块应被视为：

- 外部工具客户端接入层；
- 对早期 MCP 调用方式的兼容实现；
- GraphML 和工具 schema 的参考实现。

在本项目内部新增业务功能时，优先改造 `backend/vector_index_system/`、`backend/education/` 和 `backend/maintenance/`。只有需要 MCP 客户端调用时，才同步扩展本模块。

## 配置

默认配置位于 `backend/mcp-server/config.py`，常见变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MCP_SERVER_HOST` | `localhost` | MCP 服务主机 |
| `MCP_SERVER_PORT` | `8000` | MCP 服务端口 |

MCP 客户端可参考 `mcp_config_example.py` 配置命令、参数和环境变量。

## 数据注意事项

- `backend/mcp-server/data/*.db` 和 SQLite 派生文件已被 `.gitignore` 忽略。
- 如果需要提交示例数据，应使用小型 JSON 或 GraphML 示例，并确认来源许可证。
- 本模块不得内置真实 API key 或本机绝对路径。

## 扩展规则

1. 新增工具时，先定义 Pydantic 参数模型。
2. 工具返回值应为可 JSON 序列化对象。
3. 图谱 schema 变更时，同步维护 `backend/vector_index_system/` 和维护 API。
4. 如果工具依赖第三方仓库实现，需要在 `THIRD_PARTY.md` 中记录来源和许可证。
