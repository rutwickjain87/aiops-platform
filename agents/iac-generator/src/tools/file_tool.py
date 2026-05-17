"""
src/tools/file_tool.py — Write generated Terraform files to the output directory.

Handles:
  - Creating the output directory if it does not exist
  - Writing each .tf file with UTF-8 encoding
  - Returning the list of written absolute paths
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def write_terraform_files(files: dict[str, str], output_dir: str) -> list[str]:
    """
    Write generated .tf file contents to output_dir.

    Args:
        files:       dict mapping filename → HCL content
        output_dir:  destination directory (created if it doesn't exist)

    Returns:
        List of absolute paths of written files.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    written = []
    for filename, content in files.items():
        path = out / filename
        path.write_text(content, encoding="utf-8")
        written.append(str(path.resolve()))
        log.info("Wrote %s (%d chars)", path, len(content))

    return written
