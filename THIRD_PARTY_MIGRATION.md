# 第三方运行时迁移说明

这个文件记录的是：如何把历史上直接拷进仓库的第三方图谱/记忆系统，逐步收敛成“外部依赖 + 本项目自有适配层”的结构。

## 当前判断

仓库已经把下面这些大体积或外部来源目录视为本地资产，不应作为常规源码提交：

- `backend/vector_index_system/memory_systems/`
- `backend/vector_index_system/models/`
- `backend/vector_index_system/vector_index/`

`.gitignore` 也已经按这个方向配置。

## 迁移目标

目标不是把所有能力都删掉，而是把结构改成：

1. 本项目只保留自己的适配层和桥接代码
2. 第三方实现通过 `pip`、独立 checkout 或显式外部路径提供
3. 模型权重、向量索引、缓存和实验仓库不跟随主仓库版本化

## 需要重点处理的目录

| 目录 | 建议状态 |
| --- | --- |
| `mem0/` | 优先改成外部依赖，例如 `mem0ai` |
| `graphrag_hybrid/` | 作为外部研究依赖或独立仓库，不直接拷贝进主仓库 |
| `aws_graphrag/` | 保留项目自有适配层，外部实现从独立来源提供 |
| `openclaw-engram/` | 优先视为外部工作区或独立依赖，而不是仓库内副本 |

## 当前应保留的项目自有代码

以下代码属于项目自己的运行时或桥接层，应继续留在主仓库：

- `core/memory_runtime.py`
- `core/cli_dispatch.py`
- `core/bridge.py`
- `backend/vector_index_system/graph_service.py`
- `backend/vector_index_system/README.md`

## 推荐迁移步骤

1. 先确认根目录 `requirements.txt` 只保留单端口主流程真正需要的最小依赖
2. 把每个第三方能力收敛成一个“项目适配器 + 外部提供方”的组合
3. 停止把完整上游源码、模型权重、生成索引直接纳入主仓库
4. 如果移除了某个提供方，同步检查 `core/memory_runtime.py` 的发现与回退逻辑
5. 在对应 README 中明确哪些目录是“兼容层”，哪些才是主实现

## 不再沿用的旧说明

- `requirements_new.txt` 不存在，不应再作为迁移步骤前提
- “删除目录再验证”这种表述过于粗糙，应该先完成适配层与依赖方式切换，再处理仓库内副本
