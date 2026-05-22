"""Teacher supplement parser: parse teacher-supplied content and update the knowledge graph."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from KGTS.core.graph_manager import KnowledgeGraph


class TeacherSupplementParser:

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def parse_and_update(self, supplement_content: str, chapter_id: Optional[str] = None,
                        teacher_id: str = "teacher_001") -> Dict:
        results = {
            "success": True,
            "created_nodes": [],
            "updated_nodes": [],
            "created_relations": [],
            "created_notes": []
        }

        note = self.kg.add_node(
            content=supplement_content,
            type="note",
            metadata={
                "source": "teacher_supplement",
                "teacher_id": teacher_id,
                "chapter_id": chapter_id,
                "created_at": datetime.now().isoformat()
            }
        )
        results["created_notes"].append(note.__dict__)

        if chapter_id:
            self.kg.add_relation(
                source_id=chapter_id,
                target_id=note.id,
                relation_type="contains",
                metadata={"source": "teacher_supplement"}
            )
            results["created_relations"].append({
                "source": chapter_id,
                "target": note.id,
                "type": "contains"
            })

        concepts = self._extract_concepts(supplement_content)

        for concept_text in concepts:
            existing = self.kg.search_nodes(concept_text, node_type="concept", limit=1)

            if existing:
                self.kg.update_node(
                    node_id=existing[0].id,
                    metadata={
                        **existing[0].metadata,
                        "supplement_ref": note.id,
                        "last_supplemented": datetime.now().isoformat()
                    }
                )
                results["updated_nodes"].append(existing[0].id)
            else:
                concept_node = self.kg.add_node(
                    content=concept_text,
                    type="concept",
                    metadata={
                        "source": "teacher_supplement",
                        "supplement_ref": note.id,
                        "chapter_id": chapter_id
                    }
                )
                results["created_nodes"].append(concept_node.__dict__)

                self.kg.add_relation(
                    source_id=note.id,
                    target_id=concept_node.id,
                    relation_type="contains"
                )

        return results

    def _extract_concepts(self, text: str) -> List[str]:
        sentences = [s.strip() for s in text.split('。') if s.strip()]
        concepts = [s + '。' for s in sentences if len(s) > 10]
        return concepts[:5]

    def get_supplements_by_chapter(self, chapter_id: str) -> List[Dict]:
        relations = self.kg.get_relations(chapter_id)

        supplement_ids = []
        for rel in relations:
            if rel.relation_type == "contains":
                node = self.kg.get_node(rel.target_id)
                if node and node.type == "note" and node.metadata.get("source") == "teacher_supplement":
                    supplement_ids.append(node.id)

        supplements = []
        for sid in supplement_ids:
            node = self.kg.get_node(sid)
            if node:
                supplements.append(node.__dict__)

        return supplements
