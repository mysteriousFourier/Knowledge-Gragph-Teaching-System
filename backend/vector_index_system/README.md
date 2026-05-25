# 图谱与向量子系统

`backend/vector_index_system/` 保存知识图谱后台页面、默认图谱数据库位置，以及一部分历史遗留的图谱/向量/记忆子系统资产。

它仍然参与当前项目运行，但这里不再是唯一的图谱主实现来源。

## 当前角色

| 路径 / 文件 | 作用 |
| --- | --- |
| `knowledge_graph/` | 图谱后台页面与默认图谱数据库目录 |
| `backend_admin.py` | 图谱后台页启动入口 |
| `graph_service.py` | 兼容 shim，主实现已转到 `core/graph_service.py` |
| `memory_runtime.py` | 记忆提供方发现与调度 |
| `run_system.py` | 历史交互式启动器 |

## 访问方式

### 单端口模式

- 图谱后台：`http://127.0.0.1:8000/admin`
- React 图谱浏览页：`http://127.0.0.1:8000/graph`

### 独立后台页

```bash
python backend/vector_index_system/backend_admin.py --port 8080
```

## 与当前主实现的关系

- 图谱读写主逻辑：`core/graph_service.py`
- 前后端桥接：`core/bridge.py`
- 兼容入口：`render_app.py`

也就是说，这个目录现在更像“仍在使用的资产目录 + 兼容层”，而不是唯一的核心业务目录。

图谱上传、导入和结构化同步接口由当前 API 路由处理。排查上传失败时，应在仓库根目录前台运行 `python render_app.py` 查看日志，而不是静默启动后台服务。

## 本地资产边界

以下内容通常是本地或大体积资产，不应作为常规版本化内容维护：

- `memory_systems/`
- `models/`
- `vector_index/`
- 生成出的缓存、索引和大模型权重

仓库已经通过 `.gitignore` 把这些内容视为本地资产。

## 部署边界

Azure App Service F1 和 Azure for Students 免费 VM 不应上传 `models/`、`vector_index/` 或大型 embedding 缓存。线上默认用：

```text
KGTS_RETRIEVAL_MODE=sparse_hybrid
```

只有本地或高资源 VM 才建议安装 `requirements-vector.txt` 并启用 `hybrid`。

## 相关说明

- [第三方依赖迁移说明](../../THIRD_PARTY_MIGRATION.md)
- [检索模式说明](../../docs/retrieval-modes.md)
