"""
GraphML文件解析器
用于解析和导入GraphML格式的知识图谱文件
"""
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class GraphMLNode:
    """GraphML节点"""
    id: str
    label: str
    type: str
    content: str
    source: str
    confidence: float
    reviewed: bool
    metadata: Dict[str, Any]


@dataclass
class GraphMLEdge:
    """GraphML边"""
    source: str
    target: str
    relation_type: str
    strength: float
    description: str
    source_type: str
    reviewed: bool
    metadata: Dict[str, Any]


class GraphMLParser:
    """GraphML文件解析器"""

    def __init__(self):
        self.namespace = {"ns": "http://graphml.graphdrawing.org/xmlns"}

    def parse_file(self, file_path: str) -> tuple[List[GraphMLNode], List[GraphMLEdge]]:
        """解析GraphML文件

        Args:
            file_path: GraphML文件路径

        Returns:
            (节点列表, 边列表)
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except ET.ParseError:
            # 如果标准XML解析失败，使用正则表达式解析
            return self._parse_with_regex(file_path)

        nodes = []
        edges = []

        # 解析节点
        for node_elem in root.findall(".//ns:node", self.namespace):
            node = self._parse_node(node_elem)
            if node:
                nodes.append(node)

        # 解析边
        for edge_elem in root.findall(".//ns:edge", self.namespace):
            edge = self._parse_edge(edge_elem)
            if edge:
                edges.append(edge)

        return nodes, edges

    def _parse_with_regex(self, file_path: str) -> tuple[List[GraphMLNode], List[GraphMLEdge]]:
        """使用正则表达式解析（处理格式不规范的GraphML）"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        nodes = []
        edges = []

        # 解析节点
        node_pattern = r'<node[^>]*id="([^"]+)">.*?</node>'
        for match in re.finditer(node_pattern, content, re.DOTALL):
            node_text = match.group(0)
            node_id = match.group(1)
            node = self._parse_node_text(node_text, node_id)
            if node:
                nodes.append(node)

        # 解析边
        edge_pattern = r'<edge[^>]*source="([^"]+)"[^>]*target="([^"]+)"[^>]*>.*?</edge>'
        for match in re.finditer(edge_pattern, content, re.DOTALL):
            edge_text = match.group(0)
            source = match.group(1)
            target = match.group(2)
            edge = self._parse_edge_text(edge_text, source, target)
            if edge:
                edges.append(edge)

        return nodes, edges

    def _parse_node(self, node_elem) -> Optional[GraphMLNode]:
        """解析单个节点元素"""
        node_id = node_elem.get("id")
        if not node_id:
            return None

        data = self._extract_data(node_elem)
        label = data.get("label", node_id)
        node_type = data.get("type", "concept")
        content = data.get("content", label)
        source = data.get("source", "")
        confidence = float(data.get("confidence", 1.0))
        reviewed = data.get("reviewed", "0") == "1"

        # 确保元数据中包含label
        metadata = {
            "label": label,
            "source": source,
            "confidence": confidence,
            "reviewed": reviewed
        }
        # 如果content不同于label，也添加到metadata中
        if content and content != label:
            metadata["content"] = content

        return GraphMLNode(
            id=node_id,
            label=label,
            type=node_type,
            content=content,
            source=source,
            confidence=confidence,
            reviewed=reviewed,
            metadata=metadata
        )

    def _parse_edge(self, edge_elem) -> Optional[GraphMLEdge]:
        """解析单个边元素"""
        source = edge_elem.get("source")
        target = edge_elem.get("target")

        if not source or not target:
            return None

        data = self._extract_data(edge_elem)
        relation_type = data.get("rtype", "related")
        strength = float(data.get("strength", 1.0))
        description = data.get("description", "")
        source_type = data.get("rsource", "")
        reviewed = data.get("rreviewed", "0") == "1"

        metadata = {
            "description": description,
            "strength": strength,
            "source": source_type,
            "reviewed": reviewed
        }

        return GraphMLEdge(
            source=source,
            target=target,
            relation_type=relation_type,
            strength=strength,
            description=description,
            source_type=source_type,
            reviewed=reviewed,
            metadata=metadata
        )

    def _parse_node_text(self, node_text: str, node_id: str) -> Optional[GraphMLNode]:
        """从文本中解析节点"""
        data = self._extract_data_text(node_text)
        label = data.get("label", node_id)
        node_type = data.get("type", "concept")
        content = data.get("content", label)
        source = data.get("source", "")
        confidence = float(data.get("confidence", 1.0))
        reviewed = data.get("reviewed", "0") == "1"

        metadata = {
            "label": label,
            "source": source,
            "confidence": confidence,
            "reviewed": reviewed
        }

        return GraphMLNode(
            id=node_id,
            label=label,
            type=node_type,
            content=content,
            source=source,
            confidence=confidence,
            reviewed=reviewed,
            metadata=metadata
        )

    def _parse_edge_text(self, edge_text: str, source: str, target: str) -> Optional[GraphMLEdge]:
        """从文本中解析边"""
        data = self._extract_data_text(edge_text)
        relation_type = data.get("rtype", "related")
        strength = float(data.get("strength", 1.0))
        description = data.get("description", "")
        source_type = data.get("rsource", "")
        reviewed = data.get("rreviewed", "0") == "1"

        metadata = {
            "description": description,
            "strength": strength,
            "source": source_type,
            "reviewed": reviewed
        }

        return GraphMLEdge(
            source=source,
            target=target,
            relation_type=relation_type,
            strength=strength,
            description=description,
            source_type=source_type,
            reviewed=reviewed,
            metadata=metadata
        )

    def _extract_data(self, element) -> Dict[str, str]:
        """从元素中提取所有data标签"""
        data = {}
        for data_elem in element.findall(".//ns:data", self.namespace):
            key = data_elem.get("key")
            # 使用itertext来获取所有文本内容，包括子元素的文本
            text = ''.join(data_elem.itertext()).strip()
            data[key] = text
        return data

    def _extract_data_text(self, text: str) -> Dict[str, str]:
        """从文本中提取所有data标签（支持多行内容）"""
        data = {}
        pattern = r'<data key="([^"]+)">([\s\S]*?)</data>'
        for match in re.finditer(pattern, text):
            key = match.group(1)
            value = match.group(2).strip()
            data[key] = value
        return data


def parse_graphml_file(file_path: str) -> tuple[List[GraphMLNode], List[GraphMLEdge]]:
    """解析GraphML文件的便捷函数

    Args:
        file_path: GraphML文件路径

    Returns:
        (节点列表, 边列表)
    """
    parser = GraphMLParser()
    return parser.parse_file(file_path)


def convert_to_mcp_format(nodes: List[GraphMLNode], edges: List[GraphMLEdge]) -> Dict[str, Any]:
    """将GraphML数据转换为MCP格式

    Args:
        nodes: GraphML节点列表
        edges: GraphML边列表

    Returns:
        MCP格式的图谱数据
    """
    mcp_nodes = []
    mcp_edges = []

    # 类型映射 - 支持更多类型
    type_mapping = {
        "chapter": "chapter",
        "proposition": "concept",
        "derivation": "note",
        "discussion": "observation",
        "concept": "concept",
        "note": "note",
        "observation": "observation"
    }

    for node in nodes:
        # 转换节点类型
        mcp_type = type_mapping.get(node.type, "concept")

        # 构建元数据，确保包含label和description
        metadata = node.metadata.copy()
        if "label" not in metadata:
            metadata["label"] = node.label
        if "description" not in metadata:
            metadata["description"] = node.content

        mcp_nodes.append({
            "id": node.id,
            "content": node.content,
            "type": mcp_type,
            "metadata": metadata
        })

    for edge in edges:
        # 关系类型映射
        rel_type_mapping = {
            "belongs_to": "contains",
            "precedes": "precedes"
        }
        mcp_rel_type = rel_type_mapping.get(edge.relation_type, edge.relation_type)

        mcp_edges.append({
            "source_id": edge.source,
            "target_id": edge.target,
            "relation_type": mcp_rel_type,
            "metadata": edge.metadata,
            "similarity": edge.strength if edge.strength < 1.0 else None
        })

    return {
        "nodes": mcp_nodes,
        "edges": mcp_edges,
        "stats": {
            "node_count": len(mcp_nodes),
            "relation_count": len(mcp_edges)
        }
    }
