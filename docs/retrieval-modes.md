# 检索模式说明

KGTS 当前支持三种图谱检索模式。

## 本地默认：`hybrid`

本地启动脚本默认使用 GraphRAG hybrid：FAISS embedding 向量索引先召回图谱节点，再沿图关系补充公式、例题、表格、前后置节点并重排。树选择仍是生成边界，PPT/TeX、逐页讲解、授课文案和问答会优先使用统一的 GraphRAG 上下文。

先安装可选依赖：

```bash
python -m pip install -r requirements/vector.txt
```

低内存 Linux VM 使用 CPU-only 依赖文件，避免 PyPI 自动拉取 CUDA 版 torch：

```bash
python -m pip install -r requirements/vector-cpu.txt
```

本地默认配置：

```text
KGTS_RETRIEVAL_MODE=hybrid
KGTS_VECTOR_INDEX_DIR=.runtime/vector_index
KGTS_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
KGTS_EMBEDDING_CACHE_DIR=.runtime/huggingface
KGTS_EMBEDDING_LOCAL_FILES_ONLY=1
KGTS_VECTOR_STARTUP_ENSURE=0
KGTS_PROJECT_LOCAL_ONLY=1
```

`KGTS_EMBEDDING_LOCAL_FILES_ONLY=1` 会要求模型已经在本机缓存或路径可用。`KGTS_PROJECT_LOCAL_ONLY=1` 会把索引和 HuggingFace/SentenceTransformer 缓存固定在项目目录内，推荐把模型预先放到 `.runtime/huggingface` 或把 `KGTS_EMBEDDING_MODEL` 指向 `models/embeddings/...`。缺失时接口会在 `vector_stats.last_error` / `retrieval_stats.last_error` 中返回明确错误，不会假装成功降级成 `graph_db`。

默认 `KGTS_VECTOR_STARTUP_ENSURE=0`，Web 服务启动不会主动加载 embedding 模型；第一次混合检索或手动重建索引时才会加载。需要本地开发时预热索引，可以改成 `KGTS_VECTOR_STARTUP_ENSURE=1`。

## `graph_db`

轻量兼容模式。它使用 SQLite 知识图谱和文本打分，不依赖向量模型。保留给本地排障和兼容场景；当前 Azure 默认不使用它。

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

`sparse_hybrid` 不是神经网络 embedding 检索，但可以在不增加部署体积的情况下提供实用的“图谱 + 向量式”混合检索。当前 Azure 默认仍保持 `hybrid`，不会主动切到该模式。

## 低资源 Azure 部署说明

Azure App Service F1 不适合让神经 embedding 大模型常驻主进程。线上保持 `hybrid`，但用 CPU-only 依赖、启动不预热、查询/重建后释放模型引用：

```text
KGTS_RETRIEVAL_MODE=hybrid
KGTS_VECTOR_STARTUP_ENSURE=0
KGTS_VECTOR_UNLOAD_AFTER_QUERY=1
KGTS_VECTOR_UNLOAD_AFTER_REBUILD=1
KGTS_VECTOR_HASH_FALLBACK=1
```

GitHub Actions 的 Azure App Service 部署包会排除这些大型本地资产：

- `backend/vector_index_system/models/`
- `backend/vector_index_system/vector_index/`
- `backend/vector_index_system/memory_systems/`

重型向量依赖不要放在 `requirements.txt` 中。它们已拆到 `requirements/vector.txt` / `requirements/vector-cpu.txt`；Azure workflow 安装 `requirements/vector-cpu.txt`，避免拉取 CUDA 版 torch。

Azure for Students 1 GB VM 保持 `hybrid`，但应按错峰运行处理：TTS 朗读课件时不要触发向量重建，备课/问答需要向量检索时让 TTS 代理空闲。推荐配置：

```text
KGTS_RETRIEVAL_MODE=hybrid
KGTS_VECTOR_STARTUP_ENSURE=0
KGTS_VECTOR_UNLOAD_AFTER_QUERY=1
KGTS_VECTOR_UNLOAD_AFTER_REBUILD=1
```

这会避免 Web 服务启动预加载 embedding，并在每次查询/重建后释放 SentenceTransformer 模型引用。FAISS 索引仍可保留在内存中，成本远低于 torch 模型。Azure for Students VM 的具体部署配置见 [Azure for Students VM 部署](azure-student-vm.md)。
