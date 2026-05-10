"""Lecture note manager: store, query, and update AI-generated lecture notes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from KGTS.core.graph_manager import KnowledgeGraph


class LectureNoteManager:

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def store_lecture_note(self, content: str, chapter_id: str, teacher_id: str = "teacher_001",
                          metadata: Optional[Dict] = None) -> Dict:
        note_metadata = {
            "source": "ai_lecture",
            "teacher_id": teacher_id,
            "chapter_id": chapter_id,
            "created_at": datetime.now().isoformat(),
            "status": "draft",
            **(metadata or {})
        }

        note = self.kg.add_node(content, type="observation", metadata=note_metadata)

        self.kg.add_relation(
            source_id=chapter_id,
            target_id=note.id,
            relation_type="contains",
            metadata={"type": "lecture_note"}
        )

        return {
            "success": True,
            "note_id": note.id,
            "metadata": note_metadata
        }

    def get_lecture_note(self, note_id: str) -> Optional[Dict]:
        note = self.kg.get_node(note_id)
        if note and note.type == "observation":
            return note.__dict__
        return None

    def get_lecture_notes_by_chapter(self, chapter_id: str) -> List[Dict]:
        relations = self.kg.get_relations(chapter_id)

        note_ids = []
        for rel in relations:
            if rel.relation_type == "contains":
                node = self.kg.get_node(rel.target_id)
                if node and node.type == "observation" and node.metadata.get("source") == "ai_lecture":
                    note_ids.append(node.id)

        notes = []
        for nid in note_ids:
            node = self.kg.get_node(nid)
            if node:
                notes.append(node.__dict__)

        return notes

    def get_latest_lecture_note(self, chapter_id: str) -> Optional[Dict]:
        notes = self.get_lecture_notes_by_chapter(chapter_id)
        if notes:
            notes.sort(key=lambda x: x["metadata"]["created_at"], reverse=True)
            return notes[0]
        return None

    def update_lecture_note(self, note_id: str, content: Optional[str] = None,
                           metadata: Optional[Dict] = None) -> Dict:
        success = self.kg.update_node(note_id, content, metadata)
        return {
            "success": success,
            "note_id": note_id
        }

    def approve_lecture_note(self, note_id: str, teacher_id: str) -> Dict:
        note = self.kg.get_node(note_id)
        if not note:
            return {"success": False, "error": "Note not found"}

        success = self.kg.update_node(
            note_id,
            metadata={
                **note.metadata,
                "status": "approved",
                "approved_by": teacher_id,
                "approved_at": datetime.now().isoformat()
            }
        )

        return {"success": success, "note_id": note_id}

    def delete_lecture_note(self, note_id: str) -> Dict:
        success = self.kg.delete_node(note_id)
        return {"success": success, "note_id": note_id}

    def search_lecture_notes(self, keyword: str) -> List[Dict]:
        nodes = self.kg.search_nodes(keyword, node_type="observation")

        lecture_notes = [
            node.__dict__ for node in nodes
            if node.metadata.get("source") == "ai_lecture"
        ]

        return lecture_notes
