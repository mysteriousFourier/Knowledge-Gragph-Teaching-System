# 知识图谱与向量后端

`backend/vector_index_system/` 保存知识图谱存储、搜索和后台管理相关代码。当前项目主要依赖 SQLite 图谱服务和前端图谱管理页面。

## 目录说明

```text
knowledge_graph/             图谱服务、数据库逻辑和后台管理页面
models/                      本地模型目录，已忽略
memory_systems/              外部研究系统或实验仓库，已忽略
vector_index/                向量索引和缓存，已忽略
```

## 公开仓库中的边界

本目录只应提交本项目自身需要维护的代码和说明。模型权重、外部仓库副本、生成索引、SQLite 数据库和缓存文件都不应提交。

## 前端图谱页面

图谱后台页面位于：

```text
backend/vector_index_system/knowledge_graph/backend_admin.html
```

通过前端服务器访问时可打开：

```text
http://localhost:3000/backend/vector_index_system/knowledge_graph/backend_admin.html
```

更多细节见 [知识图谱与向量后端模块文档](../../docs/modules/knowledge-graph-vector.md)。
