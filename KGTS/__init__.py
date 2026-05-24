"""Compatibility package alias for test imports.

The repository can be checked out under different directory names. Some tests
import modules through the historical ``KGTS`` package name, so expose the
repository root as this package's search path.
"""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent)]
