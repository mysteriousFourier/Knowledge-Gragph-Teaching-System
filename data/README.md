# `data/`

`data/` 用于保存可以公开提交、并且适合作为项目种子或说明性资产的数据文件。

这个目录不应成为运行时脏数据、个人资料或本地缓存的堆放点。

## 应该放什么

- 可公开分发的种子数据
- 部署初始状态需要的最小数据包
- 与运行时数据边界相关的说明文档

## 不应提交什么

- 私有或临时数据库
- API Key、Token、Cookie、凭据文件
- 运行时缓存、导出文件、日志
- 未授权分发的 PDF、论文、笔记
- 个人学习记录或人工调试产物

## 当前目录约定

| 路径 | 作用 |
| --- | --- |
| `data/seed/` | 可提交的种子章节与种子图谱数据库 |
| `.runtime/` | 推荐的运行时章节、进度、日志目录 |
| `backend/vector_index_system/knowledge_graph/` | 默认本地图谱数据库位置 |

## 运行时数据位置

以下环境变量会影响实际运行时数据落点：

- `APP_RUNTIME_DIR`
- `APP_DATA_DIR`
- `GRAPH_DB_PATH`

如果没有显式覆盖，项目仍会兼容旧的本地路径布局。

## 部署约定

Azure App Service 和 Azure for Students VM 都应从 `data/seed/` 引导初始数据，再把运行时写入 `.runtime/` 或显式的 `APP_DATA_DIR` / `GRAPH_DB_PATH`。不要在生产运行中把教师反馈、学生进度、缓存和日志写回 `data/seed/`。

## 相关文档

- [种子数据说明](seed/README.md)
- [结构化课程数据说明](../structured/README.md)
- [Azure for Students VM 部署](../docs/azure-student-vm.md)
