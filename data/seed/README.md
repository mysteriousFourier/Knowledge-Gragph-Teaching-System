# 种子数据

`data/seed/` 保存可以随仓库分发的初始化数据，用于帮助新环境快速获得可用的章节内容和基础图谱数据。

## 当前文件

| 文件 | 作用 |
| --- | --- |
| `chapters.json` | 初始章节内容与练习题种子 |
| `knowledge_graph.db` | 可分发的种子图谱数据库 |
| `vector_index/` | 与种子图谱对应的预建向量索引 |

像 `chapters.json.bak-*` 这样的备份文件只是本地工作副本，不属于规范化种子集。

`vector_index/` 适合本地或资源较充足的 VM 快速启动，但 Azure App Service 的 GitHub Actions 部署包会排除它，避免把 FAISS 索引和大 metadata 塞进低资源 zip 包。App Service 线上会保留 `hybrid` 接口，并在没有可用索引或 embedding 模型时使用 hashing fallback；需要重建索引时写入 `.runtime/vector_index`。

`chapters.json` 里的练习题只作为初始数据。运行后教师端可以继续追加题目：每次生成 5 道新题，题库总量不设置上限；学生练习会从可用题库中随机抽取最多 10 题，并跳过教师点踩的题目。

## 启动时如何使用

根目录 `render_app.py` 会在启动时执行两类引导：

1. 把 `chapters.json` 合并到运行时章节文件
2. 在显式设置 `APP_DATA_DIR` 或 `GRAPH_DB_PATH` 时，必要时复制 `knowledge_graph.db`
3. 在显式设置 `KGTS_VECTOR_INDEX_DIR` 或使用默认运行时目录时，必要时复制 `vector_index/`

如果没有显式指定运行时图谱数据库路径，项目默认写入 `.runtime/knowledge_graph.db`。旧版路径只作为兼容工具目录保留。

低资源线上部署建议设置：

```text
APP_BOOTSTRAP_SEED_DATA=1
APP_RUN_STARTUP_MAINTENANCE=0
RENDER_AUTO_SYNC_STRUCTURED=0
```

这样启动时优先使用种子数据，避免在 Azure F1 或 1 GB 免费 VM 冷启动阶段做结构化全量同步。

## 维护约定

- 只保留可公开分发的数据
- 修改种子文件时，确认字段结构与当前 API 兼容
- 不要把运行时输出、个人测试数据或临时备份当成正式种子提交
- 不要把教师反馈、学生进度和运行时生成章节直接写回种子文件
