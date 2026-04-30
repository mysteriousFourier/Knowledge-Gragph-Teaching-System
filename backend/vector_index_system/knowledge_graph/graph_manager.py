#!/usr/bin/env python3
"""
知识图谱管理系统

功能：
- 知识图谱审查机制
- 人工可编辑的知识图谱提取功能
- 知识图谱可视化界面
- 知识节点和关系管理
"""

import os
import sys
import json
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# 加载环境变量
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_config import load_root_env

load_root_env()

# 尝试导入OpenAI SDK（DeepSeek使用OpenAI兼容API）
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

class KnowledgeGraphManager:
    """知识图谱管理器"""
    
    def __init__(self, data_dir: str, storage_path: str = "./knowledge_graph"):
        """
        初始化知识图谱管理器
        
        Args:
            data_dir: 结构化数据目录
            storage_path: 知识图谱存储路径
        """
        self.data_dir = data_dir
        self.storage_path = Path(storage_path)
        self.db_path = self.storage_path / "knowledge_graph.db"
        
        # 初始化存储目录
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self._init_database()
        
        # 初始化DeepSeek API客户端
        self.deepseek_client = self._init_deepseek_client()
        
        print(f"知识图谱管理器初始化完成")
        print(f"存储路径: {self.storage_path}")
        print(f"数据库路径: {self.db_path}")
    
    def _init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # 创建节点表
        cursor.executescript("""
            -- 知识节点表
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT,
                source TEXT,
                confidence REAL DEFAULT 0.0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                reviewed INTEGER DEFAULT 0
            );
            
            -- 关系表
            CREATE TABLE IF NOT EXISTS relationships (
                id TEXT PRIMARY KEY,
                source_node TEXT NOT NULL,
                target_node TEXT NOT NULL,
                type TEXT NOT NULL,
                strength REAL DEFAULT 1.0,
                description TEXT,
                source TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                reviewed INTEGER DEFAULT 0,
                FOREIGN KEY (source_node) REFERENCES nodes(id),
                FOREIGN KEY (target_node) REFERENCES nodes(id)
            );
            
            -- 审查日志表
            CREATE TABLE IF NOT EXISTS review_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                comments TEXT,
                timestamp INTEGER NOT NULL
            );
            
            -- 索引
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
            CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(type);
            CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_node);
            CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_node);
        """)
        
        conn.commit()
        conn.close()
    
    def _init_deepseek_client(self):
        """初始化DeepSeek API客户端"""
        try:
            print("初始化DeepSeek API客户端...")
            if OpenAI:
                # 从环境变量或配置文件获取API密钥
                deepseek_api_key = os.environ.get('DEEPSEEK_API_KEY', '')
                if deepseek_api_key:
                    print("使用 DeepSeek API (OpenAI兼容接口)")
                    try:
                        client = OpenAI(
                            api_key=deepseek_api_key,
                            base_url="https://api.deepseek.com"
                        )
                        print("DeepSeek API客户端初始化成功")
                        return client
                    except Exception as e:
                        print(f"创建OpenAI客户端失败: {e}")
                        print("使用模拟实现")
                else:
                    print("DeepSeek API密钥未设置，使用模拟实现")
            else:
                print("OpenAI SDK 未安装，使用模拟实现")
        except Exception as e:
            print(f"初始化DeepSeek API客户端失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 返回模拟客户端
        print("返回模拟DeepSeek客户端")
        return self._create_mock_deepseek_client()
    
    def _create_mock_deepseek_client(self):
        """创建模拟DeepSeek客户端"""
        class MockResponse:
            def __init__(self, content):
                self.choices = [{'message': {'content': content}}]
        
        class MockCompletions:
            def create(self, model, messages, **kwargs):
                return MockResponse(f"模拟回答: {messages[-1]['content']}")
        
        class MockChat:
            def __init__(self):
                self.completions_instance = MockCompletions()
            
            def completions(self):
                return self.completions_instance
        
        class MockDeepSeek:
            def __init__(self):
                self.chat_instance = MockChat()
            
            def chat_completions(self, model, messages, **kwargs):
                return MockResponse(f"模拟回答: {messages[-1]['content']}")
            
            @property
            def chat(self):
                return self.chat_instance
        
        return MockDeepSeek()

    def extract_from_structured_data(self):
        """从结构化数据中提取知识图谱"""
        print("从结构化数据中提取知识图谱...")

        data_path = Path(self.data_dir)
        if not data_path.exists():
            print(f"错误: 数据目录 {self.data_dir} 不存在")
            return False

        # 步骤1: 执行语义消歧
        print("\n步骤1: 执行语义消歧")
        from .semantic_disambiguation import SemanticDisambiguator  # 使用相对导入

        disambiguator = SemanticDisambiguator(self.data_dir)
        disambiguator.run()

        disambiguated_chunks = disambiguator.get_disambiguated_chunks()
        semantic_relations = disambiguator.get_semantic_relations()  # 获取语义关系

        # 步骤2: 从消歧后的chunks构建知识图谱（传递语义关系）
        print("\n步骤2: 从消歧后的chunks构建知识图谱")
        extracted_nodes, extracted_rels = self._build_graph_from_disambiguated_chunks(
            disambiguated_chunks,
            semantic_relations=semantic_relations  # 传递关系
        )

        print(f"\n知识图谱提取完成")
        print(f"提取节点数: {extracted_nodes}")
        print(f"提取关系数: {extracted_rels}")
        return True

    def _perform_semantic_disambiguation(self):
        """执行语义消歧"""
        # 使用相对导入（因为本文件就在 knowledge_graph 包内）
        from .semantic_disambiguation import SemanticDisambiguator

        disambiguator = SemanticDisambiguator(self.data_dir)
        disambiguator.run()

        return disambiguator.get_disambiguated_chunks(), disambiguator.get_semantic_relations()

    def _build_graph_from_disambiguated_chunks(self, disambiguated_chunks, semantic_relations=None):
        """从消歧后的chunks构建知识图谱（修复版，支持语义关系）"""
        extracted_nodes = 0
        extracted_rels = 0
        node_id_map = {}  # 用于跟踪已创建的节点，避免重复

        # 第一步：创建所有内容节点
        for chunk in disambiguated_chunks:
            try:
                content = chunk.get('content', '')
                block_type = chunk.get('block_type', 'text')
                source = chunk.get('source', '')
                chunk_id = chunk.get('id', f"chunk_{extracted_nodes}")
                metadata = chunk.get('metadata', {})
                chapter = metadata.get('chapter', 'unknown')

                if not content:
                    continue

                # 创建内容节点（使用chunk_id确保一致性）
                node_id = self._create_node_safe(
                    id=chunk_id,  # 使用chunk的ID，确保后续关系能匹配
                    label=content[:80] + "..." if len(content) > 80 else content,
                    type=block_type,
                    content=content,
                    source=source,
                    chapter=chapter
                )
                node_id_map[chunk_id] = node_id
                extracted_nodes += 1

            except Exception as e:
                print(f"处理chunk时出错: {e}")

        # 第二步：创建章节节点和章节-内容关系
        chapter_nodes = {}  # chapter_name -> node_id
        for chunk in disambiguated_chunks:
            chapter = chunk.get('metadata', {}).get('chapter', 'unknown')
            chunk_id = chunk.get('id')

            if chapter not in chapter_nodes:
                chapter_node_id = self._create_node_safe(
                    id=f"chapter_{chapter}",
                    label=f"章节: {chapter}",
                    type="chapter",
                    content=f"章节 {chapter}",
                    source="auto"
                )
                chapter_nodes[chapter] = chapter_node_id

            # 创建章节包含内容的关系
            if chunk_id in node_id_map:
                self._create_relationship_safe(
                    source_node=chapter_nodes[chapter],
                    target_node=node_id_map[chunk_id],
                    type="belongs_to",
                    description=f"属于章节 {chapter}",
                    source="structure"
                )
                extracted_rels += 1

        # 第三步：创建语义关系（关键修复！）
        if semantic_relations:
            print(f"正在创建 {len(semantic_relations)} 个语义关系...")
            for rel in semantic_relations:
                source_id = rel.get('source')
                target_id = rel.get('target')

                # 确保两个节点都存在
                if source_id in node_id_map and target_id in node_id_map:
                    self._create_relationship_safe(
                        source_node=node_id_map[source_id],
                        target_node=node_id_map[target_id],
                        type=rel.get('type', 'related'),
                        description=rel.get('description', '语义关联'),
                        strength=rel.get('strength', 0.5),
                        source="semantic_analysis"
                    )
                    extracted_rels += 1
                else:
                    print(f"跳过关系: 节点 {source_id} 或 {target_id} 不存在")

        # 第四步：基于内容相似度和DeepSeek API补充关系（如果没有足够的语义关系）
        if not semantic_relations or len(semantic_relations) < 5:
            print("基于内容相似度和DeepSeek API创建补充关系...")
            supplementary_rels = self._create_similarity_relations(disambiguated_chunks, node_id_map)
            extracted_rels += supplementary_rels
            
            # 使用DeepSeek API为无法纳入大分类的内容生成关系
            print("使用DeepSeek API为无法纳入大分类的内容生成关系...")
            deepseek_rels = self._create_relations_with_deepseek(disambiguated_chunks, node_id_map)
            extracted_rels += deepseek_rels

        print(f"\n知识图谱构建完成:")
        print(f"  - 节点数: {extracted_nodes}")
        print(f"  - 关系数: {extracted_rels}")
        print(f"  - 章节数: {len(chapter_nodes)}")

        return extracted_nodes, extracted_rels

    def _create_similarity_relations(self, chunks, node_id_map, threshold=0.4):
        """基于文本相似度创建补充关系"""
        from difflib import SequenceMatcher
        import itertools

        created = 0
        chunk_list = list(chunks)

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

        # 只处理前50个chunk以避免计算爆炸
        chunk_list = chunk_list[:50]

        for chunk1, chunk2 in itertools.combinations(chunk_list, 2):
            id1, id2 = chunk1.get('id'), chunk2.get('id')

            if id1 not in node_id_map or id2 not in node_id_map:
                continue

            # 计算文本相似度
            similarity = SequenceMatcher(None,
                                         chunk1.get('content', '')[:200],
                                         chunk2.get('content', '')[:200]).ratio()

            if similarity > threshold:
                # 尝试确定关系类型
                relation_type = self._determine_relation_type(chunk1, chunk2)
                if relation_type not in primary_relation_types:
                    relation_type = 'other'
                
                self._create_relationship_safe(
                    source_node=node_id_map[id1],
                    target_node=node_id_map[id2],
                    type=relation_type,
                    description=f"{primary_relation_types.get(relation_type, '其他关系')} (相似度: {similarity:.2f})",
                    strength=float(similarity),
                    source="similarity_analysis"
                )
                created += 1

        print(f"  - 基于相似度创建了 {created} 个补充关系")
        return created
    
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
    
    def _create_relations_with_deepseek(self, chunks, node_id_map):
        """使用DeepSeek API为无法纳入大分类的内容生成关系"""
        import itertools

        created = 0
        chunk_list = list(chunks)

        # 只处理前20个chunk以避免API调用过多
        chunk_list = chunk_list[:20]

        for chunk1, chunk2 in itertools.combinations(chunk_list, 2):
            id1, id2 = chunk1.get('id'), chunk2.get('id')

            if id1 not in node_id_map or id2 not in node_id_map:
                continue

            # 获取节点内容
            content1 = chunk1.get('content', '')
            content2 = chunk2.get('content', '')

            # 使用DeepSeek API生成关系
            rel_result = self.generate_relationship_with_deepseek(
                node_id_map[id1],
                node_id_map[id2],
                content1,
                content2
            )

            if rel_result:
                try:
                    rel_type = rel_result.get('relationship_type', 'related_to')
                    description = rel_result.get('description', 'DeepSeek生成的关系')
                    strength = rel_result.get('strength', 0.5)

                    # 创建关系
                    self._create_relationship_safe(
                        source_node=node_id_map[id1],
                        target_node=node_id_map[id2],
                        type=rel_type,
                        description=description,
                        strength=strength,
                        source="deepseek_analysis"
                    )
                    created += 1
                except Exception as e:
                    print(f"创建DeepSeek生成的关系失败: {e}")

        print(f"  - 基于DeepSeek API创建了 {created} 个关系")
        return created

    def _create_node_safe(self, id, label, type, content, source, chapter=None):
        """安全的节点创建（带ID检查），支持自定义ID"""
        # 检查是否已存在相同ID的节点
        existing = self.get_node_by_custom_id(id)
        if existing:
            return existing['id']

        # 创建新节点（使用自定义ID，不使用hash）
        timestamp = int(__import__('time').time())

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO nodes (id, label, type, content, source, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (id, label, type, content, source, 1.0, timestamp, timestamp))
            conn.commit()
            return id
        except Exception as e:
            print(f"创建节点失败: {e}")
            conn.rollback()
            return id
        finally:
            conn.close()

    def _create_relationship_safe(self, source_node, target_node, type, description, strength=1.0, source="auto"):
        """安全的关系创建（避免重复），支持strength"""
        # 检查是否已存在相同的关系
        existing = self._get_relationship(source_node, target_node, type)
        if existing:
            return existing['id']

        # 创建新关系（包含strength），使用基于实体ID的有意义ID
        # 格式: [source_node]_[type]_[target_node]
        rel_id = f"[{source_node}]_{type}_{target_node}"
        timestamp = int(__import__('time').time())

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO relationships (id, source_node, target_node, type, strength, description, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (rel_id, source_node, target_node, type, strength, description, source, timestamp, timestamp))
            conn.commit()
            return rel_id
        except Exception as e:
            print(f"创建关系失败: {e}")
            conn.rollback()
            return rel_id
        finally:
            conn.close()

    def get_node_by_custom_id(self, custom_id):
        """根据自定义ID（即节点的id字段）获取节点"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT id, label, type, content FROM nodes WHERE id = ?", (custom_id,))
            row = cursor.fetchone()
            if row:
                return {"id": row[0], "label": row[1], "type": row[2], "content": row[3]}
            return None
        finally:
            conn.close()

    def _get_relationship(self, source_node, target_node, rel_type):
        """检查关系是否存在"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT id FROM relationships 
                WHERE source_node = ? AND target_node = ? AND type = ?
            """, (source_node, target_node, rel_type))
            row = cursor.fetchone()
            if row:
                return {"id": row[0]}
            return None
        finally:
            conn.close()
    
    def generate_relationship_with_deepseek(self, source_node_id, target_node_id, source_content, target_content):
        """
        使用DeepSeek API生成两个节点之间的关系
        
        Args:
            source_node_id: 源节点ID
            target_node_id: 目标节点ID
            source_content: 源节点内容
            target_content: 目标节点内容
        
        Returns:
            生成的关系类型和描述
        """
        try:
            # 构建提示
            prompt = f"""
            分析以下两个内容之间的关系，并返回一个合适的关系类型和描述。
            
            内容1: {source_content}
            内容2: {target_content}
            
            请返回JSON格式，包含以下字段：
            - relationship_type: 关系类型（如：related_to, part_of, causes, explains等）
            - description: 关系的详细描述
            - strength: 关系强度（0-1之间的数值）
            """
            
            # 调用DeepSeek API
            if hasattr(self.deepseek_client, 'chat_completions'):
                response = self.deepseek_client.chat_completions(
                    model="deepseek-chat",
                    messages=[{'role': 'user', 'content': prompt}]
                )
                content = response.choices[0].message.content
            elif hasattr(self.deepseek_client, 'chat'):
                response = self.deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{'role': 'user', 'content': prompt}]
                )
                content = response.choices[0].message.content
            else:
                return None
            
            # 解析响应
            import json
            result = json.loads(content)
            return result
        except Exception as e:
            print(f"使用DeepSeek API生成关系失败: {e}")
            return None
    
    def get_nodes(self, type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取节点列表"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            if type:
                cursor.execute("""
                    SELECT id, label, type, content, source, confidence, created_at, updated_at, reviewed
                    FROM nodes WHERE type = ? LIMIT ?
                """, (type, limit))
            else:
                cursor.execute("""
                    SELECT id, label, type, content, source, confidence, created_at, updated_at, reviewed
                    FROM nodes LIMIT ?
                """, (limit,))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "label": row[1],
                    "type": row[2],
                    "content": row[3],
                    "source": row[4],
                    "confidence": row[5],
                    "created_at": row[6],
                    "updated_at": row[7],
                    "reviewed": row[8]
                })
            return results
        except Exception as e:
            print(f"获取节点列表失败: {e}")
            return []
        finally:
            conn.close()
    
    def get_relationships(self, type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取关系列表"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            if type:
                cursor.execute("""
                    SELECT id, source_node, target_node, type, strength, description, source, created_at, updated_at, reviewed
                    FROM relationships WHERE type = ? LIMIT ?
                """, (type, limit))
            else:
                cursor.execute("""
                    SELECT id, source_node, target_node, type, strength, description, source, created_at, updated_at, reviewed
                    FROM relationships LIMIT ?
                """, (limit,))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "source_node": row[1],
                    "target_node": row[2],
                    "type": row[3],
                    "strength": row[4],
                    "description": row[5],
                    "source": row[6],
                    "created_at": row[7],
                    "updated_at": row[8],
                    "reviewed": row[9]
                })
            return results
        except Exception as e:
            print(f"获取关系列表失败: {e}")
            return []
        finally:
            conn.close()
    
    def review_entity(self, entity_type: str, entity_id: str, reviewer: str, 
                     action: str, comments: str = "") -> bool:
        """审查实体"""
        timestamp = int(datetime.now().timestamp())
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            # 记录审查日志
            cursor.execute("""
                INSERT INTO review_logs (entity_type, entity_id, action, reviewer, comments, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (entity_type, entity_id, action, reviewer, comments, timestamp))
            
            # 更新实体的审查状态
            if entity_type == "node":
                cursor.execute("UPDATE nodes SET reviewed = 1, updated_at = ? WHERE id = ?", (timestamp, entity_id))
            elif entity_type == "relationship":
                cursor.execute("UPDATE relationships SET reviewed = 1, updated_at = ? WHERE id = ?", (timestamp, entity_id))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"审查实体失败: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_unreviewed_entities(self, entity_type: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取未审查的实体"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            if entity_type == "node":
                cursor.execute("""
                    SELECT id, label, type, content, source, confidence, created_at, updated_at
                    FROM nodes WHERE reviewed = 0 LIMIT ?
                """, (limit,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "id": row[0],
                        "label": row[1],
                        "type": row[2],
                        "content": row[3],
                        "source": row[4],
                        "confidence": row[5],
                        "created_at": row[6],
                        "updated_at": row[7]
                    })
                return results
            
            elif entity_type == "relationship":
                cursor.execute("""
                    SELECT id, source_node, target_node, type, strength, description, source, created_at, updated_at
                    FROM relationships WHERE reviewed = 0 LIMIT ?
                """, (limit,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "id": row[0],
                        "source_node": row[1],
                        "target_node": row[2],
                        "type": row[3],
                        "strength": row[4],
                        "description": row[5],
                        "source": row[6],
                        "created_at": row[7],
                        "updated_at": row[8]
                    })
                return results
            
            return []
        except Exception as e:
            print(f"获取未审查实体失败: {e}")
            return []
        finally:
            conn.close()
    
    def export_graph(self, format: str = "json") -> Any:
        """导出知识图谱"""
        if format == "json":
            return self._export_json()
        elif format == "graphml":
            return self._export_graphml()
        else:
            return None
    
    def _export_json(self) -> Dict[str, Any]:
        """导出为JSON格式"""
        graph = {
            "nodes": self.get_nodes(limit=1000),
            "relationships": self.get_relationships(limit=1000)
        }
        return graph
    
    def _export_graphml(self) -> str:
        """导出为GraphML格式"""
        graphml = '''<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="label" for="node" attr.name="label" attr.type="string"/>
  <key id="type" for="node" attr.name="type" attr.type="string"/>
  <key id="content" for="node" attr.name="content" attr.type="string"/>
  <key id="source" for="node" attr.name="source" attr.type="string"/>
  <key id="confidence" for="node" attr.name="confidence" attr.type="double"/>
  <key id="reviewed" for="node" attr.name="reviewed" attr.type="boolean"/>
  <key id="rtype" for="edge" attr.name="type" attr.type="string"/>
  <key id="strength" for="edge" attr.name="strength" attr.type="double"/>
  <key id="description" for="edge" attr.name="description" attr.type="string"/>
  <key id="rsource" for="edge" attr.name="source" attr.type="string"/>
  <key id="rreviewed" for="edge" attr.name="reviewed" attr.type="boolean"/>
  <graph id="G" edgedefault="directed">
'''
        
        # 添加节点
        for node in self.get_nodes(limit=1000):
            graphml += f'''    <node id="{node['id']}">
      <data key="label">{node['label']}</data>
      <data key="type">{node['type']}</data>
      <data key="content">{node['content']}</data>
      <data key="source">{node['source']}</data>
      <data key="confidence">{node['confidence']}</data>
      <data key="reviewed">{node['reviewed']}</data>
    </node>
'''
        
        # 添加关系
        for rel in self.get_relationships(limit=1000):
            graphml += f'''    <edge id="{rel['id']}" source="{rel['source_node']}" target="{rel['target_node']}">
      <data key="rtype">{rel['type']}</data>
      <data key="strength">{rel['strength']}</data>
      <data key="description">{rel['description']}</data>
      <data key="rsource">{rel['source']}</data>
      <data key="rreviewed">{rel['reviewed']}</data>
    </edge>
'''
        
        graphml += '''  </graph>
</graphml>'''
        return graphml
    
    def import_graph(self, data: Dict[str, Any]) -> bool:
        """导入知识图谱"""
        try:
            # 导入节点
            for node in data.get('nodes', []):
                self.add_node(
                    label=node['label'],
                    type=node['type'],
                    content=node.get('content', ''),
                    source=node.get('source', 'import')
                )
            
            # 导入关系
            for rel in data.get('relationships', []):
                self.add_relationship(
                    source_node=rel['source_node'],
                    target_node=rel['target_node'],
                    type=rel['type'],
                    description=rel.get('description', ''),
                    source=rel.get('source', 'import')
                )
            
            return True
        except Exception as e:
            print(f"导入知识图谱失败: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        stats = {}
        
        try:
            # 节点统计
            cursor.execute("SELECT COUNT(*) FROM nodes")
            stats["total_nodes"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM nodes WHERE reviewed = 1")
            stats["reviewed_nodes"] = cursor.fetchone()[0]
            
            # 关系统计
            cursor.execute("SELECT COUNT(*) FROM relationships")
            stats["total_relationships"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM relationships WHERE reviewed = 1")
            stats["reviewed_relationships"] = cursor.fetchone()[0]
            
            # 节点类型分布
            cursor.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type")
            stats["node_types"] = {}
            for row in cursor.fetchall():
                stats["node_types"][row[0]] = row[1]
            
            # 关系类型分布
            cursor.execute("SELECT type, COUNT(*) FROM relationships GROUP BY type")
            stats["relationship_types"] = {}
            for row in cursor.fetchall():
                stats["relationship_types"][row[0]] = row[1]
            
            return stats
        except Exception as e:
            print(f"获取统计信息失败: {e}")
            return {}
        finally:
            conn.close()

def test_init():
    """测试初始化功能"""
    print("开始测试初始化...")
    try:
        import os
        import sys
        print(f"Python版本: {sys.version}")
        print(f"当前目录: {os.getcwd()}")
        
        # 测试知识图谱管理器初始化
        structured_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "structured")
        print(f"结构化数据路径: {structured_path}")
        print(f"路径是否存在: {os.path.exists(structured_path)}")
        
        print("初始化KnowledgeGraphManager...")
        manager = KnowledgeGraphManager(structured_path)
        print("知识图谱管理器初始化成功！")
        
        # 获取统计信息
        print("获取统计信息...")
        stats = manager.get_stats()
        print("知识图谱统计信息:")
        print(stats)
        
        print("测试完成！")
        return True
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        print("测试失败！")
        return False

if __name__ == "__main__":
    # 测试初始化
    test_init()
    
    # 测试知识图谱管理器
    # manager = KnowledgeGraphManager("../../structured")
    # 
    # # 从结构化数据提取知识图谱
    # manager.extract_from_structured_data()
    # 
    # # 获取统计信息
    # stats = manager.get_stats()
    # print("知识图谱统计信息:")
    # print(stats)
    # 
    # # 导出知识图谱
    # graph_json = manager.export_graph("json")
    # print(f"导出节点数: {len(graph_json['nodes'])}")
    # print(f"导出关系数: {len(graph_json['relationships'])}")
