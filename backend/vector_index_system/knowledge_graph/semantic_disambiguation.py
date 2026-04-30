#!/usr/bin/env python3
"""
语义消歧模块

功能：
- 对chunks知识聚类进行语义消歧
- 分析聚类后知识块间的语义关系
- 识别并解决潜在的歧义问题
- 确保知识表示的准确性和一致性
- 排除formula库相关内容的参与
"""

import os
import json
import re
import sys
import numpy as np
from typing import List, Dict, Any, Tuple
from pathlib import Path
from collections import defaultdict

# 加载环境变量
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_config import load_root_env

load_root_env()


class SemanticDisambiguator:
    """语义消歧器"""

    def __init__(self, data_dir: str):
        """
        初始化语义消歧器

        Args:
            data_dir: 结构化数据目录
        """
        self.data_dir = data_dir
        self.chunks = []
        self.clusters = []
        self.disambiguated_chunks = []
        self.semantic_relations = []  # 新增：存储语义关系

        print("语义消歧器初始化完成")
        print(f"数据目录: {data_dir}")

    def load_chunks(self):
        """加载chunks数据，排除formula库相关内容"""
        print("加载chunks数据...")

        data_path = Path(self.data_dir)
        if not data_path.exists():
            print(f"错误: 数据目录 {self.data_dir} 不存在")
            return False

        loaded_chunks = 0

        for file_path in data_path.glob('*.json'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # 排除formula库相关内容
                    source_title = data.get('metadata', {}).get('source_title', '')
                    if 'formula' in source_title.lower():
                        print(f"跳过formula库内容: {source_title}")
                        continue

                    # 处理blocks内容
                    blocks = data.get('blocks', [])
                    for block in blocks:
                        content = block.get('content', '')
                        block_type = block.get('type', 'text')

                        # 处理所有类型的block，只要有内容
                        if content:
                            chunk = {
                                'id': f"{file_path.stem}_{block.get('id', loaded_chunks)}",
                                'content': content,
                                'source': str(file_path),
                                'block_type': block_type,
                                'metadata': data.get('metadata', {}),
                                'chapter': data.get('metadata', {}).get('chapter', 'unknown'),
                                'keywords': self._extract_keywords(content)
                            }
                            self.chunks.append(chunk)
                            loaded_chunks += 1

            except Exception as e:
                print(f"处理 {file_path} 时出错: {e}")

        print(f"加载完成，共加载 {loaded_chunks} 个chunks")
        return True

    def cluster_chunks(self):
        """对chunks进行聚类"""
        print("对chunks进行聚类...")

        # 简单的基于主题的聚类
        clusters = defaultdict(list)

        for chunk in self.chunks:
            # 使用章节作为基础聚类
            chapter = chunk.get('chapter', '其他')
            clusters[chapter].append(chunk)

        # 转换为聚类列表
        self.clusters = [{'name': str(name), 'chunks': chunks} for name, chunks in clusters.items()]

        print(f"聚类完成，共 {len(self.clusters)} 个聚类")
        for i, cluster in enumerate(self.clusters):
            print(f"聚类 {i + 1}: {cluster['name']} (包含 {len(cluster['chunks'])} 个chunks)")

        return True

    def analyze_semantic_relations(self):
        """分析chunks之间的语义关系（新增方法）"""
        print("分析语义关系...")

        relations = []

        # 1. 同聚类内的关系（强关联）
        for cluster in self.clusters:
            chunks = cluster['chunks']
            for i, chunk1 in enumerate(chunks):
                for j, chunk2 in enumerate(chunks):
                    if i < j:
                        similarity = self._calculate_similarity(chunk1['content'], chunk2['content'])
                        if similarity > 0.3:  # 相似度阈值
                            # 确定关系类型
                            relation_type = self._determine_relation_type(chunk1, chunk2)
                            relations.append({
                                'source': chunk1['id'],
                                'target': chunk2['id'],
                                'type': relation_type,
                                'strength': float(similarity),
                                'description': f"同章节关联 (相似度: {similarity:.2f})",
                                'cluster': cluster['name']
                            })

        # 2. 跨聚类的关键词关联（发现隐藏关系）
        all_chunks = self.chunks
        for i, chunk1 in enumerate(all_chunks):
            for j, chunk2 in enumerate(all_chunks):
                if i < j and chunk1['chapter'] != chunk2['chapter']:  # 不同章节
                    # 关键词重叠分析
                    keywords1 = set(chunk1['keywords'])
                    keywords2 = set(chunk2['keywords'])
                    common_keywords = keywords1 & keywords2

                    if len(common_keywords) >= 2:  # 至少2个共同关键词
                        strength = len(common_keywords) / max(len(keywords1), len(keywords2))
                        # 确定关系类型
                        relation_type = self._determine_relation_type(chunk1, chunk2)
                        relations.append({
                            'source': chunk1['id'],
                            'target': chunk2['id'],
                            'type': relation_type,
                            'strength': float(strength),
                            'description': f"语义关联: {', '.join(list(common_keywords)[:3])}",
                            'cluster': f"{chunk1['chapter']} - {chunk2['chapter']}"
                        })

        # 3. 内容类型特定的关系
        for chunk in self.chunks:
            if chunk['block_type'] == 'formula':
                # 公式与上下文的关系
                # 找到同章节的文本块作为解释
                same_chapter_texts = [
                    c for c in self.chunks
                    if c['chapter'] == chunk['chapter'] and c['block_type'] == 'text'
                ]
                if same_chapter_texts:
                    # 连接到最近的文本块（简化处理：第一个）
                    relations.append({
                        'source': same_chapter_texts[0]['id'],
                        'target': chunk['id'],
                        'type': 'explains',
                        'strength': 0.8,
                        'description': "文本解释公式",
                        'cluster': chunk['chapter']
                    })

        self.semantic_relations = relations
        print(f"语义关系分析完成，共发现 {len(relations)} 个关系")
        return relations
    
    def _determine_relation_type(self, chunk1, chunk2):
        """确定两个chunk之间的关系类型"""
        content1 = chunk1.get('content', '').lower()
        content2 = chunk2.get('content', '').lower()
        block_type1 = chunk1.get('block_type', '').lower()
        block_type2 = chunk2.get('block_type', '').lower()
        metadata1 = chunk1.get('metadata', {})
        metadata2 = chunk2.get('metadata', {})
        chapter1 = metadata1.get('chapter', '').lower()
        chapter2 = metadata2.get('chapter', '').lower()
        
        # 定义主要关系类型
        primary_relation_types = {
            'belongs_to': '表示属于某个类别或章节',
            'part_of': '表示是某个整体的一部分',
            'uses': '表示使用了某个概念或公式',
            'relates_to': '表示与某个概念相关',
            'derived_from': '表示从某个公式或定理推导而来',
            'supports': '表示支持某个定理或概念',
            'describes': '表示描述了某个概念或定理'
        }
        
        # 检查是否是章节与内容的关系
        if chapter1 and not chapter2:
            return 'belongs_to'
        if chapter2 and not chapter1:
            return 'belongs_to'
        
        # 检查是否是公式与章节的关系
        if 'formula' in block_type1 or 'equation' in block_type1:
            if chapter2:
                return 'belongs_to'
        if 'formula' in block_type2 or 'equation' in block_type2:
            if chapter1:
                return 'belongs_to'
        
        # 检查是否是定理与公式的关系
        if 'theorem' in block_type1 or 'theorem' in content1:
            if 'formula' in block_type2 or 'equation' in block_type2:
                return 'uses'
        if 'theorem' in block_type2 or 'theorem' in content2:
            if 'formula' in block_type1 or 'equation' in block_type1:
                return 'uses'
        
        # 检查是否是概念与概念的关系
        if block_type1 == 'concept' and block_type2 == 'concept':
            return 'relates_to'
        
        # 检查是否是定理与定理的关系
        if ('theorem' in block_type1 or 'theorem' in content1) and ('theorem' in block_type2 or 'theorem' in content2):
            return 'relates_to'
        
        # 检查是否是概念与公式的关系
        if block_type1 == 'concept' and ('formula' in block_type2 or 'equation' in block_type2):
            return 'uses'
        if block_type2 == 'concept' and ('formula' in block_type1 or 'equation' in block_type1):
            return 'uses'
        
        # 检查是否是章节与公式的关系
        if chapter1 and ('formula' in block_type2 or 'equation' in block_type2):
            return 'belongs_to'
        if chapter2 and ('formula' in block_type1 or 'equation' in block_type1):
            return 'belongs_to'
        
        # 检查是否是章节与概念的关系
        if chapter1 and block_type2 == 'concept':
            return 'belongs_to'
        if chapter2 and block_type1 == 'concept':
            return 'belongs_to'
        
        # 检查是否是定理与概念的关系
        if ('theorem' in block_type1 or 'theorem' in content1) and block_type2 == 'concept':
            return 'describes'
        if ('theorem' in block_type2 or 'theorem' in content2) and block_type1 == 'concept':
            return 'describes'
        
        # 检查是否是公式与公式的关系
        if (('formula' in block_type1 or 'equation' in block_type1) and 
            ('formula' in block_type2 or 'equation' in block_type2)):
            return 'relates_to'
        
        # 检查是否是公式与定理的关系
        if (('formula' in block_type1 or 'equation' in block_type1) and 
            ('theorem' in block_type2 or 'theorem' in content2)):
            return 'derived_from'
        if (('formula' in block_type2 or 'equation' in block_type2) and 
            ('theorem' in block_type1 or 'theorem' in content1)):
            return 'derived_from'
        
        # 检查是否是推导与定理的关系
        if block_type1 == 'derivation' and ('theorem' in block_type2 or 'theorem' in content2):
            return 'supports'
        if block_type2 == 'derivation' and ('theorem' in block_type1 or 'theorem' in content1):
            return 'supports'
        
        # 检查是否是推导与公式的关系
        if block_type1 == 'derivation' and ('formula' in block_type2 or 'equation' in block_type2):
            return 'derived_from'
        if block_type2 == 'derivation' and ('formula' in block_type1 or 'equation' in block_type1):
            return 'derived_from'
        
        # 检查是否是命题与定理的关系
        if block_type1 == 'proposition' and ('theorem' in block_type2 or 'theorem' in content2):
            return 'supports'
        if block_type2 == 'proposition' and ('theorem' in block_type1 or 'theorem' in content1):
            return 'supports'
        
        # 检查是否是命题与概念的关系
        if block_type1 == 'proposition' and block_type2 == 'concept':
            return 'describes'
        if block_type2 == 'proposition' and block_type1 == 'concept':
            return 'describes'
        
        # 检查是否是讨论与其他内容的关系
        if block_type1 == 'discussion':
            if block_type2 == 'proposition':
                return 'discusses'
            elif block_type2 == 'derivation':
                return 'analyzes'
            elif block_type2 == 'chapter':
                return 'belongs_to'
        if block_type2 == 'discussion':
            if block_type1 == 'proposition':
                return 'discussed_by'
            elif block_type1 == 'derivation':
                return 'analyzed_by'
            elif block_type1 == 'chapter':
                return 'contains'
        
        # 检查是否是命题与推导的关系
        if block_type1 == 'proposition' and block_type2 == 'derivation':
            return 'supported_by'
        if block_type2 == 'proposition' and block_type1 == 'derivation':
            return 'supports'
        
        # 检查是否是推导与推导的关系
        if block_type1 == 'derivation' and block_type2 == 'derivation':
            if 'based on' in content1 or 'based on' in content2:
                return 'based_on'
            elif 'leads to' in content1 or 'leads to' in content2:
                return 'leads_to'
            else:
                return 'relates_to'
        
        # 检查是否是命题与命题的关系
        if block_type1 == 'proposition' and block_type2 == 'proposition':
            if 'implies' in content1 or 'implies' in content2:
                return 'implies'
            elif 'contradicts' in content1 or 'contradicts' in content2:
                return 'contradicts'
            else:
                return 'relates_to'
        
        # 默认返回other
        return 'other'

    def disambiguate_clusters(self):
        """对聚类进行语义消歧"""
        print("对聚类进行语义消歧...")

        for cluster in self.clusters:
            print(f"处理聚类: {cluster['name']}")

            # 识别歧义
            ambiguities = self._identify_ambiguities(cluster['chunks'], [])

            # 解决歧义
            for chunk in cluster['chunks']:
                chunk_ambiguities = [amb for amb in ambiguities if chunk['id'] in amb.get('chunks', [])]

                if chunk_ambiguities:
                    resolved_chunk = self._resolve_chunk_ambiguity(chunk, chunk_ambiguities)
                    self.disambiguated_chunks.append(resolved_chunk)
                else:
                    chunk['disambiguated'] = True
                    chunk['ambiguity_resolved'] = 0
                    self.disambiguated_chunks.append(chunk)

        print(f"语义消歧完成，共处理 {len(self.disambiguated_chunks)} 个chunks")
        return True

    def _extract_keywords(self, text: str) -> List[str]:
        """提取文本关键词"""
        text = re.sub(r'[.,;:!?()\[\]{}"\']', ' ', text)
        text = text.lower()
        words = text.split()
        stop_words = set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'with', 'by',
                          '的', '是', '在', '和', '了', '有', '我', '他', '她', '它', '们', '这', '那', '与', '及',
                          '或'])
        keywords = [word for word in words if word not in stop_words and len(word) > 2 and not word.isdigit()]
        return list(dict.fromkeys(keywords))[:8]  # 增加到8个关键词

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（改进版，使用关键词Jaccard + 共同词）"""
        # 提取关键词
        words1 = set(self._extract_keywords(text1))
        words2 = set(self._extract_keywords(text2))

        if not words1 or not words2:
            return 0

        # Jaccard相似度
        intersection = words1 & words2
        union = words1 | words2

        if not union:
            return 0

        jaccard = len(intersection) / len(union)

        # 考虑词频权重（出现次数多的词更重要）
        text1_words = text1.lower().split()
        text2_words = text2.lower().split()

        # 计算加权相似度
        common_words = intersection
        if not common_words:
            return jaccard * 0.5  # 只有Jaccard部分

        # 如果有共同词，增强相似度
        return min(1.0, jaccard * (1 + len(common_words) * 0.1))

    def _identify_ambiguities(self, chunks: List[Dict[str, Any]],
                              semantic_relations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """识别歧义"""
        ambiguities = []

        # 基于内容识别歧义
        for chunk in chunks:
            if self._contains_ambiguous_terms(chunk['content']):
                ambiguities.append({
                    'type': 'ambiguous_terms',
                    'chunks': [chunk['id']],
                    'reason': '包含歧义术语'
                })

        return ambiguities

    def _contains_ambiguous_terms(self, text: str) -> bool:
        """检查文本是否包含歧义术语"""
        ambiguous_terms = [
            'expression', 'selection', 'linkage', 'mapping',
            'marker', 'effect', 'variance', 'heritability'
        ]
        text_lower = text.lower()
        return any(term in text_lower for term in ambiguous_terms)

    def _resolve_chunk_ambiguity(self, chunk: Dict[str, Any],
                                 ambiguities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """解决单个chunk的歧义"""
        resolved_chunk = chunk.copy()

        for ambiguity in ambiguities:
            if ambiguity['type'] == 'ambiguous_terms':
                resolved_chunk['content'] = self._disambiguate_terms(chunk['content'])

        resolved_chunk['disambiguated'] = True
        resolved_chunk['ambiguity_resolved'] = len(ambiguities)

        return resolved_chunk

    def _disambiguate_terms(self, text: str) -> str:
        """消歧术语"""
        context_mappings = {
            'expression': {'gene': 'gene expression', 'mathematical': 'mathematical expression'},
            'selection': {'natural': 'natural selection', 'artificial': 'artificial selection'},
            'linkage': {'genetic': 'genetic linkage', 'data': 'data linkage'}
        }

        text_lower = text.lower()
        for term, contexts in context_mappings.items():
            if term in text_lower:
                for context, disambiguated in contexts.items():
                    if context in text_lower:
                        text = text.replace(term, disambiguated)
                        break
        return text

    def get_disambiguated_chunks(self) -> List[Dict[str, Any]]:
        """获取消歧后的chunks"""
        return self.disambiguated_chunks

    def get_semantic_relations(self) -> List[Dict[str, Any]]:
        """获取语义关系（新增）"""
        return self.semantic_relations

    def run(self) -> bool:
        """运行完整的语义消歧流程"""
        try:
            if not self.load_chunks():
                return False

            if not self.cluster_chunks():
                return False

            # 新增：分析语义关系
            self.analyze_semantic_relations()

            if not self.disambiguate_clusters():
                return False

            print("语义消歧流程完成")
            return True
        except Exception as e:
            print(f"语义消歧流程失败: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    disambiguator = SemanticDisambiguator("../../structured")
    disambiguator.run()

    disambiguated_chunks = disambiguator.get_disambiguated_chunks()
    semantic_relations = disambiguator.get_semantic_relations()  # 获取关系

    print(f"\n消歧后共 {len(disambiguated_chunks)} 个chunks")
    print(f"发现 {len(semantic_relations)} 个语义关系")

    # 保存消歧结果和关系
    with open("disambiguated_chunks.json", 'w', encoding='utf-8') as f:
        json.dump(disambiguated_chunks, f, ensure_ascii=False, indent=2, default=str)

    # 新增：保存语义关系
    with open("semantic_relations.json", 'w', encoding='utf-8') as f:
        json.dump(semantic_relations, f, ensure_ascii=False, indent=2, default=str)

    print("结果已保存到 disambiguated_chunks.json 和 semantic_relations.json")
