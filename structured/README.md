# Structured Data Module

`structured/` 存放可被后台维护 API 扫描的结构化教材数据，包括章节切片、公式库和表格库。

## 当前内容

- `chapter6_001.json` 到 `chapter6_022.json`
- `formula_library.json`
- `table_library.json`

这些文件可通过维护 API 的 `POST /api/maintenance/scan-structured` 同步为知识图谱节点和关系。

## 详细文档

完整说明见 [docs/modules/data-assets.md](../docs/modules/data-assets.md)。
