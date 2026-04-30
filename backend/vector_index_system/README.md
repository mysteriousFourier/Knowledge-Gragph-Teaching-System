# Knowledge Graph and Vector Module

`backend/vector_index_system/` 是项目的图谱与检索核心，负责节点关系存储、搜索、语义检索、记忆 provider 编排和后端图谱管理页。

## 核心入口

| 文件 | 说明 |
| --- | --- |
| `graph_service.py` | 统一图谱服务 |
| `memory_runtime.py` | 记忆 provider 发现和 fallback |
| `cli.py` | 图谱、记忆和 RAG 命令行工具 |
| `backend_admin.py` | 图谱管理页启动入口 |

## 常用命令

```powershell
python backend\vector_index_system\cli.py graph read
python backend\vector_index_system\cli.py graph search "向量空间"
python backend\vector_index_system\cli.py memory status
```

## 详细文档

完整说明见 [docs/modules/knowledge-graph-vector.md](../../docs/modules/knowledge-graph-vector.md)。
