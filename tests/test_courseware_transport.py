import json

from KGTS.education.courseware_transport import pack_courseware


def test_repeated_images_and_tex_are_transmitted_once_without_data_loss():
    image = "data:image/png;base64," + "A" * 4096
    tex = "\\begin{frame}x\\end{frame}" * 100
    original = {"slides": [{"images": [image], "source_tex": tex}], "assets": {"image": image}, "source_tex": tex}
    packed = pack_courseware(original)
    assert packed["strings"] == [image, tex]

    def decode(value):
        if isinstance(value, dict):
            if set(value) == {"$courseware_string"}:
                return packed["strings"][value["$courseware_string"]]
            return {key: decode(child) for key, child in value.items()}
        if isinstance(value, list):
            return [decode(child) for child in value]
        return value

    assert decode(packed["payload"]) == original
    assert original["assets"]["image"] == image
    assert len(json.dumps(packed)) < len(json.dumps(original)) * 0.6


def test_small_values_and_empty_containers_are_preserved():
    original = {"text": "short", "index": 0, "ok": True, "missing": None, "list": [], "object": {}}
    packed = pack_courseware(original)
    assert packed["strings"] == []
    assert packed["payload"] == original
