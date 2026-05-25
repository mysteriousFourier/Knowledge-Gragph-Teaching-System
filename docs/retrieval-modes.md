# 检索模式说明

KGTS 当前支持三种图谱检索模式。

## 本地默认：`hybrid`

本地启动脚本默认使用 GraphRAG hybrid：FAISS embedding 向量索引先召回图谱节点，再沿图关系补充公式、例题、表格、前后置节点并重排。树选择仍是生成边界，PPT/TeX、逐页讲解、授课文案和问答会优先使用统一的 GraphRAG 上下文。

先安装可选依赖：

```bash
python -m pip install -r requirements-vector.txt
```

本地默认配置：

```text
KGTS_RETRIEVAL_MODE=hybrid
KGTS_VECTOR_INDEX_DIR=.runtime/vector_index
KGTS_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
KGTS_EMBEDDING_CACHE_DIR=.runtime/huggingface
KGTS_EMBEDDING_LOCAL_FILES_ONLY=1
KGTS_PROJECT_LOCAL_ONLY=1
```

`KGTS_EMBEDDING_LOCAL_FILES_ONLY=1` 会要求模型已经在本机缓存或路径可用。`KGTS_PROJECT_LOCAL_ONLY=1` 会把索引和 HuggingFace/SentenceTransformer 缓存固定在项目目录内，推荐把模型预先放到 `.runtime/huggingface` 或把 `KGTS_EMBEDDING_MODEL` 指向 `models/embeddings/...`。缺失时接口会在 `vector_stats.last_error` / `retrieval_stats.last_error` 中返回明确错误，不会假装成功降级成 `graph_db`。

## `graph_db`

轻量兼容模式。它使用 SQLite 知识图谱和文本打分，不依赖向量模型。

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

## 低资源 Azure 部署说明

Azure App Service F1 和 Azure for Students 免费 VM 都不适合安装神经 embedding 大模型。线上推荐：

```text
KGTS_RETRIEVAL_MODE=sparse_hybrid
```

如果最关注冷启动和内存占用，可以退回：

```text
KGTS_RETRIEVAL_MODE=graph_db
```

GitHub Actions 的 Azure App Service 部署包会排除这些大型本地资产：

- `backend/vector_index_system/models/`
- `backend/vector_index_system/vector_index/`
- `backend/vector_index_system/memory_systems/`

重型向量依赖不要放在 `requirements.txt` 中。它们已拆到 `requirements-vector.txt`，因此 Azure F1 部署时不会安装 torch、sentence-transformers 或 faiss。

Azure for Students VM 的具体部署配置见 [Azure for Students VM 部署](azure-student-vm.md)。1 GB RAM VM 上不要启用 `hybrid`，除非已经确认模型、FAISS、swap 和冷启动时间都可接受。
