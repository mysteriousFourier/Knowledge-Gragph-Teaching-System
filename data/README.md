# 数据目录

`data/` 用于保存数据说明。实际运行产生的数据库、缓存和个人数据不应提交到仓库。

## 不应提交的数据

- `.db`、`.sqlite`、`.sqlite3` 数据库。
- 运行缓存和临时 JSON。
- 个人学习记录。
- API Key、Token、Cookie 或凭据。
- 未公开论文 PDF、草稿和个人笔记。

## 推荐做法

- 可公开的结构化课程数据放在 `structured/`。
- 运行时数据放在 `.runtime/` 或后端本地数据目录。
- 单端口部署的数据可通过 `APP_RUNTIME_DIR`、`APP_DATA_DIR`、`GRAPH_DB_PATH` 指向持久化磁盘。
- 需要共享的数据应先确认来源、许可证和脱敏状态。

更多细节见 [数据资产模块文档](../docs/modules/data-assets.md)。
