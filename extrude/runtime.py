"""Writable application state lives outside the installed package."""

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("EXTRUDE_DATA_DIR", "data")).expanduser().resolve()
