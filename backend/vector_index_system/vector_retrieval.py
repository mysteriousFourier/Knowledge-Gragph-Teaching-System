#!/usr/bin/env python3
"""
向量检索模块

功能：
- 使用BGE模型生成文本向量嵌入
- 使用FAISS进行向量相似度搜索
- 提供向量索引的创建和管理
- 与知识图谱集成
"""

import os
import sys
import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# 尝试导入必要的库
try:
    import faiss
except ImportError:
    print("FAISS 未安装，尝试安装...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "faiss-cpu"], check=True)
    import faiss

try:
    from transformers import AutoTokenizer, AutoModel
    import torch
except ImportError:
    print("Transformers 未安装，尝试安装...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "transformers", "torch"], check=True)
    from transformers import AutoTokenizer, AutoModel
    import torch

class VectorRetriever:
    """向量检索器"""
    
    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5", index_path: str = "./vector_index"):
        """
        初始化向量检索器
        
        Args:
            model_name: 嵌入模型名称
            index_path: 向量索引存储路径
        """
        self.model_name = model_name
        self.base_dir = Path(__file__).resolve().parent
        self.model_root = Path(os.environ.get("VECTOR_MODEL_DIR", self.base_dir / "models"))
        self.index_path = Path(index_path)
        self.index_path.mkdir(parents=True, exist_ok=True)
        
        # 嵌入缓存
        self.embedding_cache = {}  # 文本到嵌入的缓存
        
        # 尝试加载模型
        try:
            # 尝试使用本地模型
            local_model_path = self._resolve_local_model_path(model_name)
            if local_model_path.exists():
                print(f"使用本地模型: {local_model_path}")
                self.tokenizer = AutoTokenizer.from_pretrained(str(local_model_path), local_files_only=True)
                self.model = AutoModel.from_pretrained(str(local_model_path), local_files_only=True)
                self.model_source = str(local_model_path)
            else:
                print(f"使用远程模型: {model_name}")
                endpoint = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
                print(f"Remote model endpoint: {endpoint}")
                self.tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=str(self.model_root))
                self.model = AutoModel.from_pretrained(model_name, cache_dir=str(self.model_root))
                self.model_source = f"{endpoint}/{model_name}"
            self.model.eval()
            self.model_available = True
            # 动态获取向量维度
            test_input = self.tokenizer("test", return_tensors="pt")
            with torch.no_grad():
                test_output = self.model(**test_input)
            self.embedding_dim = test_output.last_hidden_state.shape[-1]
        except Exception as e:
            print(f"加载模型失败: {e}")
            print("使用模拟嵌入")
            self.model_available = False
            # 默认向量维度
            self.embedding_dim = 1024
            self.model_source = "mock"
        
        # FAISS索引
        self.index = None
        self.id_to_text = {}  # 存储ID到文本的映射
        self.text_to_id = {}  # 存储文本到ID的映射
        self.next_id = 0
        
        # 加载已有的索引
        self._load_index()

    def _resolve_local_model_path(self, model_name: str) -> Path:
        configured_path = Path(model_name)
        if configured_path.exists():
            return configured_path

        candidates = [
            self.model_root / Path(model_name),
            self.model_root / model_name.replace("/", ""),
            Path.cwd() / "models" / Path(model_name),
            Path.cwd() / "models" / model_name.replace("/", ""),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _load_index(self):
        """加载已有的向量索引"""
        index_file = self.index_path / "vector_index.faiss"
        meta_file = self.index_path / "metadata.json"
        
        if index_file.exists() and meta_file.exists():
            try:
                self.index = faiss.read_index(str(index_file))
                with open(meta_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                self.id_to_text = metadata.get('id_to_text', {})
                self.text_to_id = metadata.get('text_to_id', {})
                self.next_id = metadata.get('next_id', 0)
                print(f"加载了现有的向量索引，包含 {len(self.id_to_text)} 个文本")
            except Exception as e:
                print(f"加载索引失败: {e}")
                self._create_index()
        else:
            self._create_index()
    
    def _create_index(self):
        """创建新的向量索引"""
        # 创建FAISS索引
        self.index = faiss.IndexFlatL2(self.embedding_dim)
        self.id_to_text = {}
        self.text_to_id = {}
        self.next_id = 0
        print("创建了新的向量索引")
    
    def _save_index(self):
        """保存向量索引"""
        index_file = self.index_path / "vector_index.faiss"
        meta_file = self.index_path / "metadata.json"
        
        try:
            faiss.write_index(self.index, str(index_file))
            metadata = {
                'id_to_text': self.id_to_text,
                'text_to_id': self.text_to_id,
                'next_id': self.next_id
            }
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            print(f"保存了向量索引到 {index_file}")
        except Exception as e:
            print(f"保存索引失败: {e}")
    
    def embed_text(self, text: str) -> np.ndarray:
        """
        生成文本的向量嵌入
        
        Args:
            text: 要嵌入的文本
        
        Returns:
            文本的向量嵌入
        """
        # 检查缓存
        if text in self.embedding_cache:
            return self.embedding_cache[text]
        
        if self.model_available:
            try:
                inputs = self.tokenizer(text, return_tensors="pt", max_length=512, truncation=True)
                with torch.no_grad():
                    outputs = self.model(**inputs)
                # 使用[CLS] token的嵌入作为文本表示
                embedding = outputs.last_hidden_state[:, 0, :].numpy()[0]
                # 归一化
                embedding = embedding / np.linalg.norm(embedding)
                # 缓存结果
                self.embedding_cache[text] = embedding
                return embedding
            except Exception as e:
                print(f"生成嵌入失败: {e}")
                embedding = self._mock_embedding(text)
                self.embedding_cache[text] = embedding
                return embedding
        else:
            embedding = self._mock_embedding(text)
            self.embedding_cache[text] = embedding
            return embedding
    
    def _mock_embedding(self, text: str) -> np.ndarray:
        """
        生成模拟嵌入
        
        Args:
            text: 要嵌入的文本
        
        Returns:
            模拟的向量嵌入
        """
        # 基于文本的哈希值生成模拟嵌入
        import hashlib
        hash_value = hashlib.md5(text.encode()).hexdigest()
        # 将哈希值转换为向量
        embedding = np.zeros(self.embedding_dim)
        for i in range(min(len(hash_value), self.embedding_dim)):
            embedding[i] = ord(hash_value[i]) / 255.0
        # 归一化
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding
    
    def add_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        添加文本到向量索引
        
        Args:
            text: 要添加的文本
            metadata: 文本的元数据
        
        Returns:
            文本的ID
        """
        # 检查文本是否已存在
        if text in self.text_to_id:
            return self.text_to_id[text]
        
        # 生成嵌入
        embedding = self.embed_text(text)
        
        # 添加到索引
        self.index.add(np.array([embedding]))
        
        # 更新映射
        text_id = self.next_id
        self.id_to_text[str(text_id)] = {
            'text': text,
            'metadata': metadata or {}
        }
        self.text_to_id[text] = text_id
        self.next_id += 1
        
        # 保存索引
        self._save_index()
        
        return text_id
    
    def search(self, query: str, k: int = 5) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        搜索与查询最相似的文本
        
        Args:
            query: 查询文本
            k: 返回的结果数量
        
        Returns:
            结果列表，每个元素是 (文本, 相似度, 元数据)
        """
        # 生成查询嵌入
        query_embedding = self.embed_text(query)
        
        # 搜索
        distances, indices = self.index.search(np.array([query_embedding]), k)
        
        # 处理结果
        results = []
        for i in range(len(indices[0])):
            idx = indices[0][i]
            if idx < len(self.id_to_text):
                text_info = self.id_to_text.get(str(idx), {})
                text = text_info.get('text', '')
                metadata = text_info.get('metadata', {})
                # 转换距离为相似度
                similarity = 1.0 / (1.0 + distances[0][i])
                results.append((text, similarity, metadata))
        
        return results
    
    def add_batch(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> List[int]:
        """
        批量添加文本到向量索引
        
        Args:
            texts: 要添加的文本列表
            metadatas: 文本的元数据列表
        
        Returns:
            文本的ID列表
        """
        if metadatas is None:
            metadatas = [{} for _ in texts]
        
        ids = []
        embeddings = []
        new_texts = []
        new_metadatas = []
        new_ids = []
        
        # 过滤已存在的文本
        for text, metadata in zip(texts, metadatas):
            if text not in self.text_to_id:
                new_texts.append(text)
                new_metadatas.append(metadata)
                new_ids.append(self.next_id)
                self.next_id += 1
            else:
                ids.append(self.text_to_id[text])
        
        # 批量生成嵌入
        if new_texts:
            for text in new_texts:
                embedding = self.embed_text(text)
                embeddings.append(embedding)
            
            # 批量添加到索引
            if embeddings:
                self.index.add(np.array(embeddings))
                
                # 更新映射
                for text, metadata, text_id in zip(new_texts, new_metadatas, new_ids):
                    self.id_to_text[str(text_id)] = {
                        'text': text,
                        'metadata': metadata
                    }
                    self.text_to_id[text] = text_id
                    ids.append(text_id)
                
                # 保存索引
                self._save_index()
        
        return ids
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取向量索引的统计信息
        
        Returns:
            统计信息
        """
        return {
            'index_size': len(self.id_to_text),
            'embedding_dim': self.embedding_dim,
            'model_name': self.model_name,
            'index_path': str(self.index_path)
        }
    
    def clear(self):
        """
        清空向量索引
        """
        self._create_index()
        self._save_index()
        print("向量索引已清空")

if __name__ == "__main__":
    # 测试向量检索器
    retriever = VectorRetriever()
    
    # 添加测试文本
    test_texts = [
        "机器学习是人工智能的一个分支",
        "深度学习是机器学习的一个子集",
        "神经网络是深度学习的核心",
        "自然语言处理是人工智能的一个应用领域",
        "计算机视觉是人工智能的另一个应用领域"
    ]
    
    print("添加测试文本...")
    for text in test_texts:
        retriever.add_text(text)
    
    # 测试搜索
    print("\n测试搜索:")
    query = "人工智能的应用"
    results = retriever.search(query, k=3)
    
    print(f"查询: {query}")
    print("结果:")
    for i, (text, similarity, metadata) in enumerate(results, 1):
        print(f"{i}. 相似度: {similarity:.4f}, 文本: {text}")
    
    # 打印统计信息
    print("\n统计信息:")
    print(json.dumps(retriever.get_stats(), indent=2, ensure_ascii=False))
