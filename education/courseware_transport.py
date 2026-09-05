"""Intern repeated large strings without removing any editable courseware data."""
from typing import Any


def pack_courseware(value: Any) -> dict[str, Any]:
    strings: list[str] = []
    indices: dict[str, int] = {}

    def encode(item: Any) -> Any:
        if isinstance(item, str) and len(item) >= 1024:
            if item not in indices:
                indices[item] = len(strings)
                strings.append(item)
            return {"$courseware_string": indices[item]}
        if isinstance(item, dict):
            return {key: encode(child) for key, child in item.items()}
        if isinstance(item, list):
            return [encode(child) for child in item]
        return item

    payload = encode(value)
    return {"encoding": "courseware-strings-v1", "payload": payload, "strings": strings}
