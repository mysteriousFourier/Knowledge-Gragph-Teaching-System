# 后台维护 API 模块

后台维护 API 位于 `backend/maintenance/`，默认运行在 `http://127.0.0.1:8002`。该模块面向知识图谱维护、结构化资料同步、导入导出、校验和后台分析。

## 主要文件

| 文件 | 职责 |
| --- | --- |
| `api_server.py` | FastAPI 入口，定义维护接口 |
| `structured_sync.py` | 扫描 `structured/`，生成节点、关系和教师端包 |
| `import_chapter.py` | 章节导入辅助逻辑 |
| `graph_query.py` | 图谱结构、节点、关系、邻居查询 |
| `graph_search.py` | 关键词、语义和混合搜索 |
| `graph_update.py` | 节点和关系增删改 |
| `teacher_supplement.py` | 教师补充内容解析 |
| `lecture_note_manager.py` | 授课文案存取和审核 |
| `mcp_client.py` | 调用 MCP 工具的兼容客户端 |
| `main.py` | 命令行演示入口 |

## 主要接口

### 基础接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/` | 服务信息 |
| `GET` | `/api/health` | 健康检查 |

### 节点和关系维护

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/maintenance/add-node` | 添加节点 |
| `PUT` | `/api/maintenance/update-node` | 更新节点 |
| `DELETE` | `/api/maintenance/delete-node` | 删除节点 |
| `POST` | `/api/maintenance/add-relation` | 添加关系 |
| `PUT` | `/api/maintenance/update-relation` | 更新关系 |
| `GET` | `/api/maintenance/get-node` | 获取节点 |
| `GET` | `/api/maintenance/relations` | 获取关系 |

### 图谱读取和搜索

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/maintenance/graph` | 获取完整图谱 |
| `POST` | `/api/maintenance/search-nodes` | 关键词搜索 |
| `POST` | `/api/maintenance/review-search` | 面向审核场景的搜索 |
| `POST` | `/api/maintenance/semantic-search` | 语义搜索 |
| `GET` | `/api/maintenance/schema` | 获取图谱 schema |
| `GET` | `/api/maintenance/subgraph` | 按类型或条件获取子图 |
| `GET` | `/api/maintenance/k-hop-neighbors` | 获取 k 跳邻居 |
| `GET` | `/api/maintenance/prerequisites` | 获取前置知识 |
| `GET` | `/api/maintenance/follow-up` | 获取后续知识 |

### 导入导出和校验

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/maintenance/import-graph` | 批量导入节点和关系 |
| `POST` | `/api/maintenance/scan-structured` | 扫描 `structured/` 并同步图谱 |
| `POST` | `/api/maintenance/import-graphml` | 导入 GraphML |
| `POST` | `/api/maintenance/visualize-graphml` | 解析 GraphML 供前端预览 |
| `GET` | `/api/maintenance/export-graph` | 导出图谱 |
| `GET` | `/api/maintenance/export-teacher-package` | 导出教师端图谱包 |
| `GET` | `/api/maintenance/analytics` | 获取统计分析 |
| `POST` | `/api/maintenance/validate-graph` | 校验图谱结构 |
| `POST` | `/api/maintenance/clean-orphans` | 清理孤立节点 |

## 结构化同步

`structured_sync.py` 将 `structured/` 中的章节、公式和表格文件转换为图谱节点与关系。同步结果会写入图谱数据库，并生成：

- `backend/data/structured_sync_manifest.json`
- `backend/data/teacher_memory_package.json`

同步流程：

```text
读取 structured/*.json
  -> 构建 SourceSpec
  -> 生成 chapter / chunk / formula / table 节点
  -> 生成 contains / references / semantic_weak 等关系
  -> 写入 GraphService
  -> 更新 manifest 和教师端包
```

## 数据模型

常见节点类型：

- `chapter`
- `concept`
- `chunk`
- `formula`
- `table`
- `note`
- `observation`

常见关系类型：

- `contains`
- `prerequisite`
- `precedes`
- `references`
- `semantic_weak`
- `related`

具体关系会经过图谱层的规范化逻辑处理，避免同义关系散落成多个 schema。

## 与其他模块的关系

- 教师端通过维护 API 查询和更新图谱。
- 教育 API 通过 `vector_backend_bridge.py` 间接使用图谱检索结果。
- 图谱数据最终由 `backend/vector_index_system/graph_service.py` 读写。
- `structured/` 是可提交的源数据目录，运行期导出的数据库和缓存默认不提交。

## 扩展规则

- 新增维护接口时，应在 FastAPI 请求模型中定义明确字段。
- 修改节点或关系 schema 时，需要同步更新 `kg_constraints.py`、前端图谱渲染逻辑和本文档。
- 导入外部数据前，应确认数据来源和许可证，并记录到 `THIRD_PARTY.md`。
