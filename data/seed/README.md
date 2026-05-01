# 部署种子数据

本目录保存可公开的部署种子数据，用于托管环境首次启动时补齐运行时状态。

- `chapters.json` 保存当前可部署的章节缓存和已批准题库。
- `knowledge_graph.db` 保存当前可部署的 SQLite 知识图谱。

运行时数据仍然被 Git 忽略。单端口 FastAPI 应用只会在部署运行目录的数据不完整时，把这些种子文件补入 `APP_RUNTIME_DIR` 和 `APP_DATA_DIR`。
