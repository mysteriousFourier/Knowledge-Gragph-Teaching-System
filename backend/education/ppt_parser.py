"""Compatibility wrapper for the shared courseware parser."""
from KGTS.education.ppt_parser import (
    SUPPORTED_COURSEWARE_EXTENSIONS,
    SUPPORTED_COURSEWARE_FORMATS_TEXT,
    build_ppt_lecture_prompt_data,
    parse_courseware,
    parse_ppt,
    parse_zip_courseware,
)

__all__ = [
    "parse_ppt",
    "parse_courseware",
    "parse_zip_courseware",
    "build_ppt_lecture_prompt_data",
    "SUPPORTED_COURSEWARE_EXTENSIONS",
    "SUPPORTED_COURSEWARE_FORMATS_TEXT",
]
