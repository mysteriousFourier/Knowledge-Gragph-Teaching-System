# 检索模式说明

KGTS 当前支持三种图谱检索模式。

## `graph_db`

默认模式。它使用 SQLite 知识图谱和轻量文本打分，不依赖向量模型。

适用场景：

- 部署到 Azure App Service F1 免费实例
- 没有 embedding 模型
- 没有 FAISS 索引
- 最关注冷启动速度和部署包大小

## `sparse_hybrid`

面向受限部署环境的免费、无模型图谱向量式检索。

它使用：

- Python 标准库构建 token 和字符 n-gram 稀疏向量
- 文本重叠打分
- 图谱关系密度重排

它不需要：

- FAISS
- numpy
- torch
- sentence-transformers
- 本地模型文件
- 外部 embedding API

Azure F1 推荐配置：

```text
KGTS_RETRIEVAL_MODE=sparse_hybrid
```

`sparse_hybrid` 不是神经网络 embedding 检索，但可以在不增加 Azure F1 部署体积的情况下提供实用的“图谱 + 向量式”混合检索。

## `hybrid`

面向本地或更高资源部署环境的神经向量 FAISS 检索。

先安装可选依赖：

```bash
python -m pip install -r requirements-vector.txt
```

再配置：

```text
KGTS_RETRIEVAL_MODE=hybrid
KGTS_VECTOR_INDEX_DIR=path/to/vector_index
KGTS_EMBEDDING_MODEL=path/or/name/of/matching_embedding_model
```

FAISS 索引和 embedding 模型必须匹配。只上传 FAISS 索引、不提供对应 embedding 模型，无法完成真正的神经向量检索，因为每次用户查询仍然需要被编码到同一个向量空间。

## Azure F1 部署说明

GitHub Actions 的 Azure 部署包会排除这些大型本地资产：

- `backend/vector_index_system/models/`
- `backend/vector_index_system/vector_index/`
- `backend/vector_index_system/memory_systems/`

重型向量依赖不要放在 `requirements.txt` 中。它们已拆到 `requirements-vector.txt`，因此 Azure F1 部署时不会安装 torch、sentence-transformers 或 faiss。
