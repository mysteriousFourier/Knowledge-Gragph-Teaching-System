from __future__ import annotations

import json
import logging
import os
import re
import uuid
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .beamer_generator_full import config
from .beamer_generator_full.deepseek_client import DeepSeekClient
from .beamer_generator_full.latex_parser import parse_latex_to_slides
from .beamer_generator_full.pptx_generator import generate_pptx
from .beamer_generator_full.prompt_engine import PromptEngine


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent / "beamer_generator_full"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

prompt_engine = PromptEngine(config.SYSTEM_PROMPT_PATH)
router = APIRouter(prefix="/beamer-generator", tags=["beamer-generator"])


class GenerateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    api_key: str = Field(default="")
    style: str = Field(default="academic")
    custom_requirements: str = Field(default="", max_length=5000)
    slide_count: int = Field(default=0, ge=0, le=50)
    language: str = Field(default="auto")
    base_url: str = Field(default="")
    model: str = Field(default="")
    figure_assets: dict[str, str] = Field(default_factory=dict)


class ParseRequest(BaseModel):
    latex: str = Field(..., min_length=1)


class SlideImage(BaseModel):
    path: str = ""
    x: float = 1.0
    y: float = 3.0
    width: float = 4.0


class SlideTextbox(BaseModel):
    text: str = ""
    x: float = 0
    y: float = 0
    width: float = 260
    height: float = 96
    color: str = "#333333"
    bg: str = ""
    fontSize: float = 14
    align: str = "left"
    bold: bool = False
    italic: bool = False


class SlidePlaceholder(BaseModel):
    type: str = "image"
    label: str = "图片占位"
    position: str = ""
    figure: str = ""
    asset: str = ""
    url: str = ""
    path: str = ""
    page: int = 0
    x: float = 570
    y: float = 150
    width: float = 245
    height: float = 230


class SlideData(BaseModel):
    id: int = 0
    type: str = "content"
    title: str = ""
    subtitle: str = ""
    items: List[str] = []
    equations: List[str] = []
    table: Optional[dict] = None
    notes: str = ""
    images: List[SlideImage] = []
    placeholders: List[SlidePlaceholder] = []
    textboxes: List[SlideTextbox] = []


class ExportRequest(BaseModel):
    title: str = "Presentation"
    subtitle: str = ""
    author: str = ""
    date: str = ""
    slides: List[SlideData] = []
    figure_assets: dict[str, str] = Field(default_factory=dict)


def _read_root_env_values() -> dict[str, str]:
    env_path = BASE_DIR.parents[1] / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _deepseek_setting(name: str, fallback: str = "") -> str:
    file_values = _read_root_env_values()
    for key, value in file_values.items():
        if key.startswith("DEEPSEEK_") and value and not os.getenv(key):
            os.environ[key] = value
    return os.getenv(name) or file_values.get(name, fallback)


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
@router.get("/index.html", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"), media_type="text/html; charset=utf-8")


@router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "beamer-generator"}


def _stream_error(message: str) -> StreamingResponse:
    async def event_stream():
        error_data = json.dumps({"type": "error", "content": message}, ensure_ascii=False)
        yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _payload_text(payload: dict, key: str, default: str = "") -> str:
    value = payload.get(key, default)
    return str(value if value is not None else default)


def _payload_int(payload: dict, key: str, default: int = 0) -> int:
    try:
        return int(payload.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _payload_map(payload: dict, key: str) -> dict[str, str]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for k, v in value.items():
        k_text = str(k or "").strip()
        v_text = str(v or "").strip()
        if k_text and v_text:
            result[k_text] = v_text
    return result


@router.post("/api/generate")
async def generate(payload: dict | None = Body(default=None)) -> StreamingResponse:
    payload = payload or {}
    content = _payload_text(payload, "content").strip()
    if not content:
        return _stream_error("请输入文案内容")

    style = _payload_text(payload, "style", "academic").strip() or "academic"
    custom_requirements = _payload_text(payload, "custom_requirements").strip()
    language = _payload_text(payload, "language", "auto").strip() or "auto"
    slide_count = max(0, min(_payload_int(payload, "slide_count", 0), 50))
    figure_assets = _payload_map(payload, "figure_assets")

    system_prompt = prompt_engine.build_system_prompt(
        style=style,
        custom_requirements=custom_requirements,
        slide_count=slide_count,
        language=language,
        figure_assets=figure_assets,
    )
    user_prompt = prompt_engine.build_user_prompt(
        content,
        custom_requirements,
        slide_count=slide_count,
        figure_assets=figure_assets,
    )
    api_key = _payload_text(payload, "api_key").strip() or _deepseek_setting("DEEPSEEK_API_KEY")
    if not api_key:
        return _stream_error("未配置 DeepSeek API Key，请先在网站右上角齿轮设置中保存 API Key")

    base_url = (
        _payload_text(payload, "base_url").strip()
        or _deepseek_setting("DEEPSEEK_API_BASE")
        or _deepseek_setting("DEEPSEEK_BASE_URL")
        or config.DEEPSEEK_BASE_URL
    )
    model = (
        _payload_text(payload, "model").strip()
        or _deepseek_setting("DEEPSEEK_PRO_MODEL")
        or _deepseek_setting("DEEPSEEK_MODEL")
        or config.DEEPSEEK_MODEL
    )
    logger.info("Generating Beamer: base_url=%s, model=%s, content_len=%s", base_url, model, len(content))
    client = DeepSeekClient(api_key=api_key, base_url=base_url)

    async def event_stream():
        yield f'data: {json.dumps({"type": "heartbeat", "content": "connected"})}\n\n'
        try:
            chunk_count = 0
            async for chunk_text in client.stream_generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                max_tokens=config.MAX_TOKENS,
                temperature=config.TEMPERATURE,
            ):
                chunk_count += 1
                data = json.dumps({"type": "chunk", "content": chunk_text}, ensure_ascii=False)
                yield f"data: {data}\n\n"
            logger.info("Beamer generation done: %s chunks", chunk_count)
            yield f'data: {json.dumps({"type": "done", "content": ""})}\n\n'
        except Exception as exc:
            logger.error("Beamer generation error: %s: %s", type(exc).__name__, exc)
            error_msg = str(exc)
            low = error_msg.lower()
            if "connect" in low or "timeout" in low:
                error_msg = f"无法连接 API ({base_url})，请检查网络或 Base URL"
            elif "401" in error_msg or "auth" in low:
                error_msg = "API Key 无效，请检查 Key 是否正确"
            elif "model" in low:
                error_msg = f"模型 '{model}' 不可用，请检查模型名称"
            error_data = json.dumps({"type": "error", "content": error_msg}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/parse-slides")
async def parse_slides(req: ParseRequest) -> JSONResponse:
    try:
        return JSONResponse(content=parse_latex_to_slides(req.latex))
    except Exception as exc:
        logger.error("Beamer parse error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


def _decode_text_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _clean_markdown_source(text: str) -> str:
    lines = []
    in_front_matter = False
    for index, line in enumerate((text or "").splitlines()):
        if index == 0 and line.strip() == "---":
            in_front_matter = True
            continue
        if in_front_matter:
            if line.strip() == "---":
                in_front_matter = False
            continue
        lines.append(line.rstrip())
    cleaned = "\n".join(lines).strip()
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned


def _normalize_package_rel_path(name: str, root_name: str = "") -> str:
    path = Path((name or "").replace("\\", "/"))
    parts = [part for part in path.parts if part not in ("", ".", "/")]
    if root_name and parts and parts[0] == root_name:
        parts = parts[1:]
    while parts and parts[0] in (".", ".."):
        parts = parts[1:]
    return "/".join(parts)


def _detect_common_root(file_names: list[str]) -> str:
    roots = []
    for name in file_names:
        parts = [part for part in Path(name.replace("\\", "/")).parts if part not in ("", ".", "/")]
        if parts:
            roots.append(parts[0])
    if not roots:
        return ""
    first = roots[0]
    if all(root == first for root in roots):
        return first
    return ""


def _rewrite_markdown_image_links(text: str, asset_urls: dict[str, str]) -> str:
    pattern = re.compile(r"(!\[[^\]]*?\]\()([^)]+)(\))")

    def replace(match: re.Match[str]) -> str:
        prefix, target, suffix = match.group(1), match.group(2), match.group(3)
        raw_target = target.strip().strip('"').strip("'")
        if raw_target.startswith(("http://", "https://", "data:", "/")):
            return match.group(0)
        normalized = raw_target.lstrip("./")
        normalized = normalized.replace("\\", "/")
        normalized = normalized.split("?", 1)[0].split("#", 1)[0]
        url = asset_urls.get(normalized)
        if not url:
            return match.group(0)
        return f"{prefix}{url}{suffix}"

    return pattern.sub(replace, text or "")


def _store_uploaded_package_files(
    files: list[UploadFile],
    package_id: str,
    require_markdown: bool = True,
) -> tuple[str, dict[str, str], str, str]:
    package_dir = UPLOAD_DIR / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    file_names = [file.filename or "" for file in files]
    root_name = _detect_common_root(file_names)
    asset_urls: dict[str, str] = {}
    markdown_bytes: bytes | None = None
    markdown_name = ""

    for upload in files:
        raw_name = upload.filename or ""
        rel_name = _normalize_package_rel_path(raw_name, root_name=root_name)
        if not rel_name:
            continue
        rel_path = Path(rel_name)
        if any(part in ("..", "") for part in rel_path.parts):
            continue

        target = package_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        data = upload.file.read()
        target.write_bytes(data)
        asset_urls[rel_path.as_posix()] = f"/beamer-generator/uploads/{package_id}/{rel_path.as_posix()}"

        if markdown_bytes is None and rel_path.suffix.lower() in {".md", ".markdown"}:
            markdown_bytes = data
            markdown_name = rel_path.name

    if markdown_bytes is None:
        if not require_markdown:
            return "", asset_urls, "", root_name
        raise HTTPException(status_code=400, detail="未找到 md / markdown 知识图谱文件")

    markdown_text = _clean_markdown_source(_decode_text_bytes(markdown_bytes))
    rewritten = _rewrite_markdown_image_links(markdown_text, asset_urls)
    return rewritten, asset_urls, markdown_name, root_name


def _extract_markdown_from_zip(data: bytes) -> tuple[str, list[str]]:
    contents: list[tuple[str, str]] = []
    with zipfile.ZipFile(BytesIO(data)) as zf:
        infos = [
            info for info in zf.infolist()
            if not info.is_dir()
            and not Path(info.filename).name.startswith("._")
            and Path(info.filename).suffix.lower() in {".md", ".markdown", ".txt"}
        ]
        infos.sort(key=lambda item: item.filename.lower())
        for info in infos:
            raw = zf.read(info)
            text = _clean_markdown_source(_decode_text_bytes(raw))
            if not text:
                continue
            title = Path(info.filename).stem
            contents.append((info.filename, f"# {title}\n\n{text}"))

    merged = "\n\n---\n\n".join(text for _name, text in contents)
    return merged, [name for name, _text in contents]


@router.post("/api/import-markdown-source")
async def import_markdown_source(file: UploadFile = File(...)):
    try:
        filename = file.filename or "source.md"
        ext = Path(filename).suffix.lower()
        content = await file.read()
        if not content:
            return JSONResponse(content={"error": "上传文件为空"}, status_code=400)

        if ext not in {".md", ".markdown"}:
            return JSONResponse(content={"error": "仅支持 .md/.markdown 知识图谱文件"}, status_code=400)

        if ext == ".zip":
            text, files = _extract_markdown_from_zip(content)
            if not text:
                return JSONResponse(content={"error": "压缩包中未找到 .md/.markdown/.txt 文件"}, status_code=400)
            return {
                "filename": filename,
                "files": files,
                "content": text,
                "char_count": len(text),
            }

        if ext not in {".md", ".markdown"}:
            return JSONResponse(content={"error": "仅支持 .md/.markdown/.txt/.zip 文件"}, status_code=400)

        text = _clean_markdown_source(_decode_text_bytes(content))
        return {
            "filename": filename,
            "files": [filename],
            "content": text,
            "char_count": len(text),
        }
    except zipfile.BadZipFile:
        return JSONResponse(content={"error": "ZIP 文件无法读取，请确认文件未损坏"}, status_code=400)
    except Exception as exc:
        logger.error("Beamer markdown import error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.post("/api/import-knowledge-package")
async def import_knowledge_package(files: List[UploadFile] = File(...)):
    try:
        if not files:
            return JSONResponse(content={"error": "未收到知识图谱文件包"}, status_code=400)

        package_id = uuid.uuid4().hex
        markdown_text, asset_urls, markdown_name, root_name = _store_uploaded_package_files(files, package_id)

        title = ""
        for line in markdown_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                break
        if not title:
            title = Path(markdown_name or root_name or "knowledge-package").stem

        return {
            "success": True,
            "file_name": markdown_name or root_name,
            "graph_type": "knowledge_package",
            "chapter_hint": {
                "title": title,
                "content": markdown_text,
            },
            "markdown_content": markdown_text,
            "parsed": {
                "nodes": 0,
                "relations": 0,
                "files": len(files),
                "assets": max(0, len(files) - 1),
            },
            "result": {
                "package_id": package_id,
                "package_name": root_name or package_id,
                "markdown_file": markdown_name,
                "asset_base_url": f"/beamer-generator/uploads/{package_id}/",
                "asset_urls": asset_urls,
            },
            "message": "知识图谱文件包导入成功",
            "imported_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Beamer knowledge package import error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.post("/api/import-image-package")
async def import_image_package(files: List[UploadFile] = File(...)):
    try:
        if not files:
            return JSONResponse(content={"error": "未收到图片包文件"}, status_code=400)

        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
        image_files = [file for file in files if Path(file.filename or "").suffix.lower() in image_exts]
        if not image_files:
            return JSONResponse(content={"error": "图片包中未找到可用图片文件"}, status_code=400)

        package_id = uuid.uuid4().hex
        _, asset_urls, _, root_name = _store_uploaded_package_files(image_files, package_id, require_markdown=False)

        return {
            "success": True,
            "graph_type": "image_package",
            "package_id": package_id,
            "package_name": root_name or package_id,
            "parsed": {
                "files": len(image_files),
                "assets": len(asset_urls),
            },
            "result": {
                "package_id": package_id,
                "package_name": root_name or package_id,
                "asset_base_url": f"/beamer-generator/uploads/{package_id}/",
                "asset_urls": asset_urls,
            },
            "message": "图片包导入成功",
            "imported_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Beamer image package import error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.post("/api/export-pptx")
async def export_pptx(req: ExportRequest) -> Response:
    try:
        pptx_bytes = generate_pptx(req.model_dump(), upload_dir=str(UPLOAD_DIR))
        return Response(
            content=pptx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": "attachment; filename=presentation.pptx"},
        )
    except Exception as exc:
        logger.error("Beamer export error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...)):
    try:
        ext = Path(file.filename or "img.png").suffix or ".png"
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = UPLOAD_DIR / filename
        content = await file.read()
        filepath.write_bytes(content)
        return {
            "url": f"/beamer-generator/uploads/{filename}",
            "filename": filename,
            "size": len(content),
        }
    except Exception as exc:
        logger.error("Beamer image upload error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)
