# 图谱与向量模块

图谱与向量模块位于 `backend/vector_index_system/`，负责知识图谱的持久化、检索、向量索引、记忆 provider 编排和后端图谱管理页。

## 主要文件

| 文件或目录 | 职责 |
| --- | --- |
| `graph_service.py` | 核心图谱服务，封装节点、关系、搜索、统计和路径查询 |
| `memory_runtime.py` | 动态发现并编排记忆 provider，支持 fallback |
| `cli.py` | 统一命令行入口，可调用图谱、记忆和 RAG 工具 |
| `backend_admin.py` | 启动后端图谱管理页 |
| `knowledge_graph/graph_viz_api.py` | 图谱管理页 HTTP API |
| `knowledge_graph/graph_manager.py` | 较底层的图谱管理逻辑 |
| `knowledge_graph/backend_admin.html` | 管理页前端 |
| `vector_retrieval.py` | 向量检索能力 |
| `graph_vector_integration.py` | 图谱和向量索引集成 |
| `llm_integration.py` | LLM 辅助分析能力 |
| `clear_cache.py` | 清理图谱缓存 |
| `config.json` | 记忆 provider 配置 |
| `knowledge_graph.graphml` | GraphML 图谱导出或交换文件 |

## 存储

默认图谱数据库：

```text
backend/vector_index_system/knowledge_graph/knowledge_graph.db
```

常见运行或生成资产：

- `knowledge_graph.graphml`
- `backend/vector_index_system/vector_index/`
- `backend/vector_index_system/models/`
- `backend/vector_index_system/memory_systems/`

本地模型、第三方研究系统、数据库和二进制索引默认不提交。

## GraphService 能力

`GraphService` 是教育 API 和维护 API 的主要底层依赖，提供：

- `read_graph()`
- `get_node()`
- `search_nodes()`
- `semantic_search()`
- `add_node()`
- `update_node()`
- `delete_node()`
- `add_relation()`
- `update_relation()`
- `delete_relation()`
- `get_neighbors()`
- `get_prerequisites()`
- `get_follow_up()`
- `get_k_hop_neighbors()`
- `get_graph_statistics()`
- `batch_import_graph()`

## 关系规范化

模块会对关系类型做规范化，避免 `parent`、`contains`、`prerequisite` 等关系出现多个拼写或同义版本。新增关系类型时，应确认教育约束、维护 API 和前端图谱都能解释该关系。

## 记忆 provider 编排

`memory_runtime.py` 会扫描 `memory_systems/` 下兼容的 provider，并构建统一的 `MemoryService`。默认配置位于 `config.json`：

```json
{
  "memory": {
    "default_provider": "mem0",
    "providers": ["mem0", "openclaw"],
    "fallback_enabled": true
  }
}
```

如果外部 provider 不存在或不可用，服务会尝试 fallback。`memory_systems/` 默认被 `.gitignore` 排除，纳入仓库前需要补充来源、许可证和改动说明。

## CLI 示例

读取图谱：

```powershell
python backend\vector_index_system\cli.py graph read
```

关键词搜索：

```powershell
python backend\vector_index_system\cli.py graph search "向量空间" --limit 10
```

语义搜索：

```powershell
python backend\vector_index_system\cli.py graph semantic-search "基和维度的关系" --top-k 5
```

RAG 问答上下文：

```powershell
python backend\vector_index_system\cli.py rag ask "什么是向量空间？"
```

记忆 provider 状态：

```powershell
python backend\vector_index_system\cli.py memory status
```

## 后端图谱管理页

启动器会运行：

```powershell
python backend\vector_index_system\backend_admin.py --port 8080
```

默认访问：

```text
http://127.0.0.1:8080/admin
```

该页面用于查看和管理图谱，不直接承担教师端或学生端业务逻辑。

## 扩展规则

- 新增图谱字段时，应保持旧数据可读，必要时在读取层做兼容。
- 新增向量索引文件或模型文件时，不应默认提交到 Git。
- 新增 provider 时，应实现 `access_entry.py` 并提供 `get_status`、`add_memory`、`search_memory` 等兼容方法。
- 修改 CLI 命令后，需要同步更新本文档和 `backend/vector_index_system/README.md`。
