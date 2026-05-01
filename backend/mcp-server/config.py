"""
MCP配置文件
"""
import os

class Config:
    # OpenClaw Memory 数据库路径（需要用户配置）
    MEMORY_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "memory.db")

    # 本地向量索引存储路径
    VECTOR_INDEX_PATH = os.path.join(os.path.dirname(__file__), "data", "vector_index.faiss")
    VECTOR_METADATA_PATH = os.path.join(os.path.dirname(__file__), "data", "vector_metadata.json")

    # 服务器配置
    HOST = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
    PORT = int(os.getenv("MCP_SERVER_PORT", "8000"))

    # 向量模型配置
    # 注意：如果无法访问HuggingFace，需要先下载模型到本地
    EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # 本地模型路径（如果已下载到本地，可以在这里指定路径）
    # EMBEDDING_MODEL = "path/to/local/model"

    # 是否使用向量搜索（如果模型下载失败，可以设为False使用关键词搜索）
    # 注意：由于网络原因，HuggingFace可能无法访问，暂时使用关键词搜索
    USE_VECTOR_SEARCH = False
    EMBEDDING_DIM = 384  # 上面模型的维度

    # 搜索配置
    TOP_K_RESULTS = 10
    SIMILARITY_THRESHOLD = 0.3

    # 日志配置
    LOG_LEVEL = "INFO"

config = Config()
