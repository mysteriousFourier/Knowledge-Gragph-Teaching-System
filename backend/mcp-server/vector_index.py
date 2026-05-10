"""
向量索引模块
使用 sentence-transformers 和 FAISS 构建语义搜索和弱关系发现
"""
import json
import os
from typing import List, Dict, Tuple, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
from config import config


class VectorIndex:
    """向量索引管理类"""

    def __init__(self):
        self.model = None
        self.index = None
        self.metadata = {}  # 存储向量ID到节点信息的映射
        self.id_to_index = {}  # 向量ID到FAISS索引的映射

        if config.USE_VECTOR_SEARCH:
            try:
                self._load_model()
                self._load_index()
            except Exception as e:
                print(f"Warning: Failed to load vector index: {e}")
                print("Falling back to keyword search only")
                self.model = None

    def _load_model(self):
        """加载embedding模型"""
        print(f"Loading embedding model: {config.EMBEDDING_MODEL}")
        self.model = SentenceTransformer(config.EMBEDDING_MODEL)
        print("Model loaded successfully")

    def _load_index(self):
        """加载已有索引"""
        if os.path.exists(config.VECTOR_INDEX_PATH) and os.path.exists(config.VECTOR_METADATA_PATH):
            self.index = faiss.read_index(config.VECTOR_INDEX_PATH)
            with open(config.VECTOR_METADATA_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.metadata = data.get('metadata', {})
                self.id_to_index = data.get('id_to_index', {})
            print("Vector index loaded successfully")
            return True
        return False

    def _save_index(self):
        """保存索引"""
        if self.index is not None:
            faiss.write_index(self.index, config.VECTOR_INDEX_PATH)
            with open(config.VECTOR_METADATA_PATH, 'w', encoding='utf-8') as f:
                json.dump({
                    'metadata': self.metadata,
                    'id_to_index': self.id_to_index
                }, f, ensure_ascii=False, indent=2)
            print("Vector index saved successfully")

    def _initialize_index(self):
        """初始化FAISS索引"""
        if self.model is None:
            return
        self.index = faiss.IndexFlatIP(config.EMBEDDING_DIM)  # 使用内积相似度
        print(f"FAISS index initialized with dimension {config.EMBEDDING_DIM}")

    def add_node(self, node_id: str, content: str, node_type: str, extra_meta: Optional[Dict] = None):
        """添加节点到向量索引"""
        if self.model is None:
            # 不使用向量搜索，只存储元数据
            self.metadata[node_id] = {
                'type': node_type,
                'content': content,
                **(extra_meta or {})
            }
            return

        if self.index is None:
            self._load_index() or self._initialize_index()

        try:
            # 生成向量
            embedding = self.model.encode(content, convert_to_numpy=True)
            embedding = embedding / np.linalg.norm(embedding)  # 归一化

            # 添加到FAISS索引
            idx = self.index.ntotal
            self.index.add(embedding.reshape(1, -1))

            # 更新映射
            self.id_to_index[node_id] = idx
            self.metadata[node_id] = {
                'type': node_type,
                'content': content,
                **(extra_meta or {})
            }

            self._save_index()
        except Exception as e:
            print(f"Warning: Failed to add node to vector index: {e}")

    def search(self, query: str, top_k: Optional[int] = None, node_type: Optional[str] = None) -> List[Dict]:
        """语义搜索"""
        if self.model is None or self.index is None or self.index.ntotal == 0:
            return []

        top_k = top_k or config.TOP_K_RESULTS

        try:
            # 生成查询向量
            query_embedding = self.model.encode(query, convert_to_numpy=True)
            query_embedding = query_embedding / np.linalg.norm(query_embedding)

            # 搜索
            similarities, indices = self.index.search(query_embedding.reshape(1, -1), min(top_k, self.index.ntotal))

            # 构建结果
            results = []
            index_to_id = {v: k for k, v in self.id_to_index.items()}

            for idx, sim in zip(indices[0], similarities[0]):
                node_id = index_to_id.get(int(idx))
                if node_id and node_id in self.metadata:
                    meta = self.metadata[node_id]

                    # 按类型过滤
                    if node_type and meta.get('type') != node_type:
                        continue

                    # 相似度阈值过滤
                    if sim < config.SIMILARITY_THRESHOLD:
                        continue

                    results.append({
                        'node_id': node_id,
                        'similarity': float(sim),
                        'metadata': meta
                    })

            return results
        except Exception as e:
            print(f"Warning: Search failed: {e}")
            return []

    def find_weak_relations(self, node_id: str, threshold: Optional[float] = None) -> List[Dict]:
        """基于向量相似度发现弱关系"""
        if self.model is None or self.index is None or node_id not in self.id_to_index:
            return []

        threshold = threshold or config.SIMILARITY_THRESHOLD

        try:
            # 获取目标节点的向量
            target_idx = self.id_to_index[node_id]
            # 从索引中提取所有向量
            all_embeddings = []
            all_ids = []

            for nid, idx in self.id_to_index.items():
                if nid != node_id:  # 排除自己
                    all_ids.append(nid)

            if not all_ids:
                return []

            # 重建索引来获取向量（简化方案）
            # 在实际生产中，应该存储所有向量
            # 这里用搜索代替
            target_meta = self.metadata[node_id]
            query = target_meta['content']
            results = self.search(query, top_k=config.TOP_K_RESULTS * 2)

            # 过滤掉强关系（直接相连的节点需要从图谱中获取）
            weak_relations = []
            for result in results:
                if result['node_id'] == node_id:
                    continue
                if result['similarity'] < threshold:
                    continue
                # 检查是否是弱关系（相似度在一定范围内，表示语义相关但不是直接关系）
                if 0.3 <= result['similarity'] <= 0.7:
                    weak_relations.append({
                        'source_id': node_id,
                        'target_id': result['node_id'],
                        'relation_type': 'semantic_weak',
                        'similarity': result['similarity'],
                        'target_metadata': result['metadata']
                    })

            return weak_relations
        except Exception as e:
            print(f"Warning: Failed to find weak relations: {e}")
            return []

    def delete_node(self, node_id: str):
        """删除节点（需要重建索引）"""
        if node_id in self.id_to_index:
            del self.id_to_index[node_id]
            del self.metadata[node_id]
            # FAISS不支持删除，需要重建索引（简化处理，实际项目可以用IndexIDMap）
            print(f"Node {node_id} removed from metadata. Index rebuild may be needed.")
            self._save_index()

    def get_statistics(self) -> Dict:
        """获取索引统计信息"""
        if self.model is None:
            return {
                'total_vectors': len(self.metadata),
                'embedding_dimension': 0,
                'model': 'disabled',
                'mode': 'keyword_only'
            }
        return {
            'total_vectors': self.index.ntotal if self.index else 0,
            'embedding_dimension': config.EMBEDDING_DIM,
            'model': config.EMBEDDING_MODEL,
            'mode': 'vector_search'
        }


# 全局向量索引实例
_vector_index = None


def get_vector_index() -> VectorIndex:
    """获取全局向量索引实例"""
    global _vector_index
    if _vector_index is None:
        _vector_index = VectorIndex()
    return _vector_index
