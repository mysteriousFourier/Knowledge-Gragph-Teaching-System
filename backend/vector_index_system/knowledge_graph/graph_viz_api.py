#!/usr/bin/env python3
"""
知识图谱可视化API

功能：
- 提供知识图谱数据的API接口
- 支持获取节点和关系数据
- 支持搜索和过滤功能
- 为前端可视化提供数据支持
"""

import os
import sys
import json
import sqlite3
from collections import Counter
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 路径修复：正确计算项目根目录
# 当前文件位置: vector_index_system/knowledge_graph/graph_viz_api.py
# 项目根目录: vector_index_system/ 的父目录
# 数据目录: 项目根目录/structured
print("Initializing graph_viz_api.py...")
print(f"Current working directory: {os.getcwd()}")
CURRENT_FILE = Path(__file__).resolve()
print(f"Current file: {CURRENT_FILE}")
KNOWLEDGE_GRAPH_DIR = CURRENT_FILE.parent
print(f"Knowledge graph directory: {KNOWLEDGE_GRAPH_DIR}")
VECTOR_INDEX_DIR = KNOWLEDGE_GRAPH_DIR.parent
print(f"Vector index directory: {VECTOR_INDEX_DIR}")
BACKEND_DIR = VECTOR_INDEX_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
print(f"Project root: {PROJECT_ROOT}")
DATA_DIR = PROJECT_ROOT / "structured"
print(f"Data directory: {DATA_DIR}")
DB_PATH = KNOWLEDGE_GRAPH_DIR / "knowledge_graph.db"
print(f"Database path: {DB_PATH}")
print(f"Database exists: {DB_PATH.exists()}")

if str(VECTOR_INDEX_DIR) not in sys.path:
    sys.path.insert(0, str(VECTOR_INDEX_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app_config import DEFAULT_BACKEND_ADMIN_PORT, get_bind_host, get_loopback_host, load_root_env  # noqa: E402
from graph_service import GraphService, PRESET_RELATION_TYPES  # noqa: E402

load_root_env()


class GraphVizAPI(BaseHTTPRequestHandler):
    """知识图谱可视化API处理类"""

    def _set_headers(self, content_type="application/json"):
        """设置HTTP响应头"""
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        """处理预检请求"""
        self._set_headers()

    def log_message(self, format, *args):
        """自定义日志"""
        from datetime import datetime
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {args[0]}")

    def _graph(self):
        return GraphService(db_path=DB_PATH)

    def _send_json(self, payload):
        self._set_headers("application/json")
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode())

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_GET(self):
        """处理GET请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query = parse_qs(parsed_path.query)

        try:
            if path == "/api/graph":
                self._handle_get_graph()
            elif path == "/api/relation-audit":
                self._handle_relation_audit()
            elif path == "/api/node":
                self._handle_get_node((query.get("node_id") or query.get("id") or [""])[0])
            elif path == "/api/relations":
                self._handle_get_relations((query.get("node_id") or [""])[0])
            elif path == "/api/nodes":
                self._handle_get_nodes()
            elif path == "/api/relationships":
                self._handle_get_relationships()
            elif path == "/api/stats":
                self._handle_get_stats()
            elif path.startswith("/api/search/"):
                search_term = path.split("/api/search/")[1]
                self._handle_search(search_term)
            elif path.startswith("/api/filter/"):
                filter_type = path.split("/api/filter/")[1]
                self._handle_filter(filter_type)
            elif path == "/" or path == "/index.html" or path == "/admin":
                self._serve_admin()
            elif path == "/viz":
                self._serve_visualization()
            else:
                self._set_headers("text/html")
                self.wfile.write(b"Not Found")
        except Exception as e:
            print(f"Error handling request: {e}")
            self._send_json({"success": False, "error": str(e)})

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        try:
            payload = self._read_json()
            graph = self._graph()
            if path == "/api/update-node":
                self._send_json(graph.update_node(
                    payload["node_id"],
                    payload.get("content"),
                    payload.get("metadata"),
                ))
            elif path == "/api/update-relation":
                self._send_json(graph.update_relation(
                    payload["relation_id"],
                    payload.get("source_id"),
                    payload.get("target_id"),
                    payload.get("relation_type"),
                    payload.get("metadata"),
                    payload.get("similarity"),
                ))
            else:
                self._send_json({"success": False, "error": f"Unknown endpoint: {path}"})
        except Exception as e:
            print(f"Error handling POST request: {e}")
            self._send_json({"success": False, "error": str(e)})

    def _handle_get_graph(self):
        graph = self._graph().read_graph()
        self._send_json({"success": True, "data": graph})

    def _handle_relation_audit(self):
        graph = self._graph().read_graph()
        nodes = graph.get("nodes", [])
        relations = graph.get("relations", [])
        structural_types = {"contains", "precedes", "references_formula", "references_table"}
        type_counts = Counter(relation.get("relation_type") or "related" for relation in relations)
        degree = Counter()
        semantic_candidate_count = 0
        for relation in relations:
            source_id = relation.get("source_id")
            target_id = relation.get("target_id")
            if source_id:
                degree[source_id] += 1
            if target_id:
                degree[target_id] += 1
            metadata = relation.get("metadata") or {}
            if metadata.get("relation_source") == "semantic_candidate":
                semantic_candidate_count += 1

        isolated = [
            {
                "id": node.get("id"),
                "label": (node.get("metadata") or {}).get("label") or node.get("label") or node.get("id"),
                "type": node.get("type"),
            }
            for node in nodes
            if degree[node.get("id")] == 0
        ]
        structural_count = sum(count for rel_type, count in type_counts.items() if rel_type in structural_types)
        semantic_count = len(relations) - structural_count
        node_count = len(nodes)
        relation_count = len(relations)
        avg_degree = round((relation_count * 2) / node_count, 2) if node_count else 0
        present_types = set(type_counts)
        self._send_json({
            "success": True,
            "audit": {
                "node_count": node_count,
                "relation_count": relation_count,
                "type_counts": dict(sorted(type_counts.items())),
                "structural_count": structural_count,
                "semantic_count": semantic_count,
                "semantic_candidate_count": semantic_candidate_count,
                "avg_degree": avg_degree,
                "isolated_count": len(isolated),
                "isolated_nodes": isolated[:40],
                "missing_preset_types": sorted(PRESET_RELATION_TYPES - present_types),
                "coverage_note": "Structural/reference relations are deterministic. Semantic relations are generated candidates and are not guaranteed exhaustive.",
            }
        })

    def _handle_get_node(self, node_id):
        if not node_id:
            self._send_json({"success": False, "error": "node_id is required"})
            return
        node = self._graph().get_node(node_id)
        self._send_json({"success": bool(node), "node": node or {}})

    def _handle_get_relations(self, node_id):
        relations = self._graph().get_relations(node_id=node_id or None)
        self._send_json({"success": True, "relations": relations, "count": len(relations)})

    def _handle_get_nodes(self):
        nodes = self._get_nodes_from_db()
        self._send_json({"success": True, "nodes": nodes, "count": len(nodes)})
        return
        """获取节点"""
        self._set_headers()

        # 如果数据库存在则读取，否则生成示例数据
        if DB_PATH.exists():
            nodes = self._get_nodes_from_db()
        else:
            nodes = self._generate_sample_nodes()
            print(f"Database not found at {DB_PATH}, using sample data")

        response = {
            "success": True,
            "nodes": nodes,
            "count": len(nodes)
        }
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode())

    def _handle_get_relationships(self):
        relationships = self._get_relationships_from_db()
        self._send_json({"success": True, "relationships": relationships, "count": len(relationships)})
        return
        """获取关系"""
        self._set_headers()

        if DB_PATH.exists():
            relationships = self._get_relationships_from_db()
        else:
            relationships = self._generate_sample_relationships()

        response = {
            "success": True,
            "relationships": relationships,
            "count": len(relationships)
        }
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode())

    def _get_nodes_from_db(self, limit=2000):
        nodes = self._graph().read_graph().get("nodes", [])[:limit]
        results = []
        for node in nodes:
            metadata = node.get("metadata") or {}
            results.append({
                "id": node.get("id"),
                "label": metadata.get("label") or node.get("label") or node.get("id"),
                "type": node.get("type"),
                "content": node.get("content"),
                "source": metadata.get("source"),
                "confidence": metadata.get("confidence", 1.0),
                "created_at": node.get("created_at"),
                "updated_at": node.get("updated_at"),
                "reviewed": bool(metadata.get("reviewed")),
                "metadata": metadata,
            })
        return results
        """从数据库获取节点"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        try:
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
                    "reviewed": bool(row[8])
                })
            return results
        finally:
            conn.close()

    def _get_relationships_from_db(self, limit=8000):
        relationships = self._graph().read_graph().get("relations", [])[:limit]
        results = []
        for relation in relationships:
            metadata = relation.get("metadata") or {}
            source_id = relation.get("source_id") or relation.get("source_node")
            target_id = relation.get("target_id") or relation.get("target_node")
            relation_type = relation.get("relation_type") or "related"
            results.append({
                "id": relation.get("id"),
                "source_node": source_id,
                "target_node": target_id,
                "source_id": source_id,
                "target_id": target_id,
                "source": source_id,
                "target": target_id,
                "type": relation_type,
                "relation_type": relation_type,
                "strength": relation.get("similarity", 1.0),
                "description": metadata.get("description", ""),
                "source_file": metadata.get("source"),
                "created_at": relation.get("created_at"),
                "updated_at": relation.get("updated_at"),
                "reviewed": bool(metadata.get("reviewed")),
                "metadata": metadata,
            })
        return results
        """从数据库获取关系"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, source_node, target_node, type, strength, description, source, created_at, updated_at, reviewed
                FROM relationships LIMIT ?
            """, (limit,))

            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "source": row[1],
                    "target": row[2],
                    "type": row[3],
                    "strength": row[4],
                    "description": row[5],
                    "source": row[6],
                    "created_at": row[7],
                    "updated_at": row[8],
                    "reviewed": bool(row[9])
                })
            return results
        finally:
            conn.close()

    def _handle_search(self, search_term):
        """搜索节点"""
        self._set_headers()

        all_nodes = self._get_nodes_from_db() if DB_PATH.exists() else self._generate_sample_nodes()

        search_lower = search_term.lower()
        filtered_nodes = [
            node for node in all_nodes
            if search_lower in node["label"].lower() or
               (node.get("content") and search_lower in node["content"].lower())
        ]

        response = {
            "success": True,
            "nodes": filtered_nodes,
            "count": len(filtered_nodes),
            "search_term": search_term
        }
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode())

    def _handle_filter(self, filter_type):
        """按类型过滤"""
        self._set_headers()

        nodes = self._get_nodes_from_db() if DB_PATH.exists() else []

        response = {
            "success": True,
            "nodes": nodes,
            "count": len(nodes),
            "filter_type": filter_type
        }
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode())

    def _handle_get_stats(self):
        """获取统计信息"""
        self._set_headers()

        if DB_PATH.exists():
            stats = self._get_stats_from_db()
        else:
            nodes = self._generate_sample_nodes()
            rels = self._generate_sample_relationships()
            stats = {
                "total_nodes": len(nodes),
                "total_relationships": len(rels),
                "reviewed_nodes": 0,
                "reviewed_relationships": 0
            }

        self.wfile.write(json.dumps(stats, ensure_ascii=False).encode())

    def _get_stats_from_db(self):
        """从数据库获取统计"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) FROM nodes")
            total_nodes = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM relationships")
            total_rels = cursor.fetchone()[0]

            return {
                "total_nodes": total_nodes,
                "total_relationships": total_rels
            }
        finally:
            conn.close()

    def _generate_sample_nodes(self):
        """生成示例节点 - 包含章节、概念、公式、方法等多种类型"""
        return [
            # 章节节点
            {"id": "1", "label": "数量遗传学", "type": "chapter", "content": "研究数量性状遗传规律的学科",
             "source": "sample"},

            # 核心概念节点
            {"id": "2", "label": "遗传力", "type": "concept", "content": "表型变异中遗传因素所占的比例",
             "source": "sample"},
            {"id": "3", "label": "表型", "type": "concept", "content": "生物体可观察的性状表现", "source": "sample"},
            {"id": "4", "label": "基因型", "type": "concept", "content": "生物体的遗传组成", "source": "sample"},

            # 公式节点
            {"id": "f1", "label": "h² = Vg/Vp", "type": "formula",
             "content": "遗传力公式：遗传方差与表型方差的比值", "source": "sample"},
            {"id": "f2", "label": "P = G + E", "type": "formula",
             "content": "表型值 = 基因型值 + 环境偏差", "source": "sample"},
            {"id": "f3", "label": "R = h²S", "type": "formula",
             "content": "育种方程：选择反应 = 遗传力 × 选择差", "source": "sample"},
            {"id": "f4", "label": "EBV = Σ(pi × ai)", "type": "formula",
             "content": "估计育种值公式", "source": "sample"},

            # 方法节点
            {"id": "5", "label": "选择育种", "type": "method", "content": "基于表型选择进行遗传改良", "source": "sample"},
            {"id": "6", "label": "QTL定位", "type": "method", "content": "数量性状位点基因定位技术", "source": "sample"},
            {"id": "7", "label": "GWAS分析", "type": "method", "content": "全基因组关联分析", "source": "sample"},
            {"id": "8", "label": "基因组选择", "type": "method", "content": "基于全基因组标记的育种值预测",
             "source": "sample"},

            # 观察/实验节点
            {"id": "o1", "label": "田间试验", "type": "observation", "content": "在田间环境下进行表型测定", "source": "sample"},
            {"id": "o2", "label": "分子标记", "type": "observation", "content": "DNA水平的遗传标记检测", "source": "sample"}
        ]

    def _generate_sample_relationships(self):
        """生成示例关系 - 包含章节-概念、概念-概念、公式-概念、方法-概念等多种关系"""
        return [
            # 章节与核心概念的关系
            {"id": "r1", "source": "1", "target": "2", "type": "包含", "strength": 1.0,
             "description": "数量遗传学包含遗传力概念"},
            {"id": "r2", "source": "1", "target": "3", "type": "研究", "strength": 0.95,
             "description": "数量遗传学研究表型"},
            {"id": "r3", "source": "1", "target": "4", "type": "研究", "strength": 0.95,
             "description": "数量遗传学研究基因型"},

            # 核心概念之间的关系
            {"id": "r4", "source": "3", "target": "4", "type": "由...决定", "strength": 0.9,
             "description": "表型由基因型决定"},
            {"id": "r5", "source": "3", "target": "2", "type": "受...影响", "strength": 0.85,
             "description": "表型受遗传力影响"},
            {"id": "r6", "source": "4", "target": "2", "type": "决定", "strength": 0.88,
             "description": "基因型决定遗传力"},

            # 公式与概念的关系（公式不仅与章节有关，还与具体概念相关）
            {"id": "f1_r1", "source": "f1", "target": "2", "type": "定义", "strength": 0.95,
             "description": "遗传力公式定义遗传力"},
            {"id": "f1_r2", "source": "f1", "target": "3", "type": "涉及", "strength": 0.8,
             "description": "遗传力公式涉及表型方差"},
            {"id": "f1_r3", "source": "f1", "target": "4", "type": "涉及", "strength": 0.8,
             "description": "遗传力公式涉及遗传方差"},
            {"id": "f2_r1", "source": "f2", "target": "3", "type": "分解", "strength": 0.9,
             "description": "表型公式分解表型值"},
            {"id": "f2_r2", "source": "f2", "target": "4", "type": "包含", "strength": 0.85,
             "description": "表型公式包含基因型值"},
            {"id": "f3_r1", "source": "f3", "target": "2", "type": "应用", "strength": 0.9,
             "description": "育种方程应用遗传力"},
            {"id": "f3_r2", "source": "f3", "target": "5", "type": "指导", "strength": 0.88,
             "description": "育种方程指导选择育种"},
            {"id": "f4_r1", "source": "f4", "target": "8", "type": "核心", "strength": 0.92,
             "description": "EBV公式是基因组选择的核心"},
            {"id": "f4_r2", "source": "f4", "target": "2", "type": "估计", "strength": 0.85,
             "description": "EBV公式估计遗传力"},

            # 公式之间的关系
            {"id": "f_r1", "source": "f2", "target": "f1", "type": "推导", "strength": 0.8,
             "description": "表型公式推导遗传力公式"},
            {"id": "f_r2", "source": "f1", "target": "f3", "type": "应用", "strength": 0.82,
             "description": "遗传力公式应用于育种方程"},

            # 方法与概念的关系
            {"id": "r7", "source": "5", "target": "3", "type": "作用于", "strength": 0.8,
             "description": "选择育种作用于表型"},
            {"id": "r8", "source": "5", "target": "2", "type": "提高", "strength": 0.82,
             "description": "选择育种提高遗传力"},
            {"id": "r9", "source": "6", "target": "1", "type": "属于", "strength": 0.9,
             "description": "QTL定位属于数量遗传学"},
            {"id": "r10", "source": "6", "target": "4", "type": "定位", "strength": 0.87,
             "description": "QTL定位定位基因型区域"},
            {"id": "r11", "source": "7", "target": "6", "type": "检测", "strength": 0.85,
             "description": "GWAS检测QTL"},
            {"id": "r12", "source": "7", "target": "3", "type": "关联", "strength": 0.83,
             "description": "GWAS关联表型变异"},
            {"id": "r13", "source": "8", "target": "7", "type": "基于", "strength": 0.9,
             "description": "基因组选择基于GWAS"},
            {"id": "r14", "source": "8", "target": "2", "type": "预测", "strength": 0.88,
             "description": "基因组选择预测遗传力"},
            {"id": "r15", "source": "8", "target": "5", "type": "优化", "strength": 0.86,
             "description": "基因组选择优化选择育种"},

            # 方法之间的关系
            {"id": "r16", "source": "7", "target": "6", "type": "发展于", "strength": 0.8,
             "description": "GWAS发展于QTL定位"},
            {"id": "r17", "source": "8", "target": "5", "type": "替代", "strength": 0.75,
             "description": "基因组选择可替代传统选择育种"},

            # 观察/实验与概念的关系
            {"id": "o1_r1", "source": "o1", "target": "3", "type": "测定", "strength": 0.85,
             "description": "田间试验测定表型"},
            {"id": "o1_r2", "source": "o1", "target": "5", "type": "支持", "strength": 0.8,
             "description": "田间试验支持选择育种"},
            {"id": "o2_r1", "source": "o2", "target": "4", "type": "标记", "strength": 0.9,
             "description": "分子标记标记基因型"},
            {"id": "o2_r2", "source": "o2", "target": "6", "type": "用于", "strength": 0.88,
             "description": "分子标记用于QTL定位"},
            {"id": "o2_r3", "source": "o2", "target": "7", "type": "用于", "strength": 0.88,
             "description": "分子标记用于GWAS分析"},
            {"id": "o2_r4", "source": "o2", "target": "8", "type": "基础", "strength": 0.9,
             "description": "分子标记是基因组选择的基础"}
        ]

    def _serve_visualization(self):
        """提供可视化界面"""
        self._set_headers("text/html")

        # 优先使用外部HTML文件，如果不存在则使用内嵌版本
        html_path = KNOWLEDGE_GRAPH_DIR / "graph_viz.html"
        if html_path.exists():
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        else:
            html_content = self._get_embedded_html()

        self.wfile.write(html_content.encode())

    def _serve_admin(self):
        self._set_headers("text/html")
        html_path = KNOWLEDGE_GRAPH_DIR / "backend_admin.html"
        if html_path.exists():
            html_content = html_path.read_text(encoding="utf-8")
        else:
            html_content = self._get_embedded_html()
        self.wfile.write(html_content.encode("utf-8"))

    def _get_embedded_html(self):
        """内嵌简化版HTML（备用）"""
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>知识图谱可视化</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body { margin: 0; font-family: Arial, sans-serif; background: #f5f5f5; }
        .container { display: flex; height: 100vh; }
        .sidebar { width: 300px; background: white; padding: 20px; box-shadow: 2px 0 5px rgba(0,0,0,0.1); }
        .main { flex: 1; position: relative; }
        svg { width: 100%; height: 100%; background: white; }
        .node circle { stroke: #fff; stroke-width: 2px; cursor: pointer; }
        .node text { font-size: 12px; pointer-events: none; }
        .link { stroke: #999; stroke-opacity: 0.6; stroke-width: 2px; }
        h1 { color: #333; font-size: 20px; margin-bottom: 20px; }
        .stat { margin: 10px 0; }
        .stat-value { font-size: 24px; color: #667eea; font-weight: bold; }
        .stat-label { font-size: 12px; color: #666; }
        input[type="text"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <h1>知识图谱可视化</h1>
            <input type="text" id="search" placeholder="搜索节点..." onkeyup="searchNodes()">
            <div class="stat">
                <div class="stat-value" id="node-count">0</div>
                <div class="stat-label">节点数量</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="edge-count">0</div>
                <div class="stat-label">关系数量</div>
            </div>
        </div>
        <div class="main">
            <svg id="graph"></svg>
        </div>
    </div>
    <script>
        let nodes = [], links = [], simulation;

        async function loadData() {
            try {
                const [nodesRes, relsRes] = await Promise.all([
                    fetch('/api/nodes'),
                    fetch('/api/relationships')
                ]);
                const nodesData = await nodesRes.json();
                const relsData = await relsRes.json();
                nodes = nodesData.nodes;
                links = relsData.relationships.map(r => ({...r, source: r.source_node, target: r.target_node}));
                document.getElementById('node-count').textContent = nodes.length;
                document.getElementById('edge-count').textContent = links.length;
                render();
            } catch(e) {
                console.error("加载数据失败:", e);
            }
        }

        function render() {
            const svg = d3.select("#graph");
            const width = svg.node().parentNode.clientWidth;
            const height = svg.node().parentNode.clientHeight;

            const g = svg.append("g");
            const zoom = d3.zoom().on("zoom", (e) => g.attr("transform", e.transform));
            svg.call(zoom);

            const color = d3.scaleOrdinal(d3.schemeCategory10);

            simulation = d3.forceSimulation(nodes)
                .force("link", d3.forceLink(links).id(d => d.id).distance(100))
                .force("charge", d3.forceManyBody().strength(-300))
                .force("center", d3.forceCenter(width/2, height/2));

            const link = g.append("g").selectAll("line").data(links)
                .enter().append("line").attr("class", "link");

            const node = g.append("g").selectAll(".node").data(nodes)
                .enter().append("g").attr("class", "node")
                .call(d3.drag().on("start", dragstarted).on("drag", dragged).on("end", dragended));

            node.append("circle").attr("r", 20).attr("fill", d => color(d.type || 0));
            node.append("text").attr("dx", 25).attr("dy", 5).text(d => d.label);

            simulation.on("tick", () => {
                link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
                    .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
                node.attr("transform", d => `translate(${d.x},${d.y})`);
            });
        }

        function dragstarted(e, d) { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }
        function dragged(e, d) { d.fx = e.x; d.fy = e.y; }
        function dragended(e, d) { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }

        function searchNodes() {
            const term = document.getElementById('search').value.toLowerCase();
            d3.selectAll('.node').style('opacity', d => 
                d.label.toLowerCase().includes(term) ? 1 : 0.1
            );
        }

        loadData();
    </script>
</body>
</html>"""


def run_server(port=DEFAULT_BACKEND_ADMIN_PORT, host=None):
    """运行API服务器"""
    try:
        # 打印启动信息
        print(f"Starting Knowledge Graph Visualization API Server...")
        print(f"Python version: {sys.version}")
        print(f"Data directory: {DATA_DIR}")
        print(f"Database: {DB_PATH}")
        print(f"Database exists: {DB_PATH.exists()}")
        
        # 测试数据库连接
        if DB_PATH.exists():
            try:
                print("Testing database connection...")
                conn = sqlite3.connect(str(DB_PATH))
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM nodes")
                node_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM relationships")
                rel_count = cursor.fetchone()[0]
                print(f"Database stats: {node_count} nodes, {rel_count} relationships")
                conn.close()
                print("Database connection test passed")
            except Exception as e:
                print(f"Database test failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Database file does not exist, will use sample data")
        
        # 启动服务器
        bind_host = host or get_bind_host("BACKEND_ADMIN_BIND_HOST")
        server_address = (bind_host, port)
        print(f"Creating HTTP server on port {port}...")
        httpd = HTTPServer(server_address, GraphVizAPI)
        
        print(f"Server created successfully")
        loopback_host = get_loopback_host()
        print(f"Running at: http://{loopback_host}:{port}")
        print(f"Visualization: http://{loopback_host}:{port}/")
        print("Press Ctrl+C to stop")
        
        # 启动服务器
        print("Starting server...")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Server error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_server()
