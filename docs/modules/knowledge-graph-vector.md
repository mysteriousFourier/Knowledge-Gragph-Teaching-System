# 知识图谱与向量后端

本模块位于 `backend/vector_index_system/`。它提供本地知识图谱存储、搜索和图谱后台页面。

## 组成

```text
knowledge_graph/             图谱服务和后台页面
models/                      本地模型目录，忽略
memory_systems/              外部研究系统或实验仓库，忽略
vector_index/                向量索引和缓存，忽略
```

## 图谱数据

图谱通常包含：

- 节点：概念、公式、章节、定理、例子。
- 关系：属于、依赖、推导、引用、相关。
- 属性：标题、正文、类型、来源、公式编号、表格编号。

前端图谱页面会把后端返回的数据归一化为节点和边，再进行可视化。

## 搜索与问答

教育 API 可以通过桥接层查询图谱后端，把图谱结果加入问答和题库生成上下文。图谱结果应作为优先证据，而不是唯一允许回答的内容。

## 忽略内容

下列内容不应提交：

- 本地模型权重。
- 向量索引。
- SQLite 数据库。
- 外部仓库副本。
- 实验缓存。

`.gitignore` 已覆盖相关路径，但提交前仍应检查 `git status`。

## 后台页面

后台页面路径：

```text
backend/vector_index_system/knowledge_graph/backend_admin.html
```

访问地址：

```text
http://127.0.0.1:3000/backend/vector_index_system/knowledge_graph/backend_admin.html
```

单端口 FastAPI 模式推荐使用：

```text
http://127.0.0.1:3000/admin
```

`render_app.py` 会把 `/admin` 映射到同一个后台页面，并提供兼容旧路径的访问方式。

该页面也需要使用统一 Markdown 和 LaTeX 渲染链路，尤其是右侧详情面板。
