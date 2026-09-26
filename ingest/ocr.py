"""On-device OCR for scanned pages, photos of documents and drawings.

Uses the Tesseract engine installed on this machine (a local binary; no
Python wrapper, no network, no model download at runtime). Output feeds the
SAME citation-verified text channel as digital text: a finding quoted from
an OCR'd page is machine-checked against the OCR transcription, and labeled
as such. Handwriting that Tesseract cannot read is still covered -- scanned
pages always also go to the local vision model (see ingest/ephemeral.py).

Low-confidence words are dropped, and a page that yields too little
confident text is treated as "no text" rather than passing OCR noise from a
photo or drawing to the drafting model as if it were real document text.
"""

from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
from typing import Optional

MIN_WORD_CONFIDENCE = 60
MIN_CONFIDENT_WORDS = 8
_TIMEOUT_SECONDS = 60


def tesseract_path() -> Optional[str]:
    return os.getenv("TESSERACT_CMD") or shutil.which("tesseract")


def ocr_available() -> bool:
    return tesseract_path() is not None


def ocr_image(image_bytes: bytes, lang: str = "eng") -> str:
    """OCR one image (any format Tesseract/Leptonica reads; PNG is safest).

    Returns the confident text, line by line, or "" if Tesseract is missing,
    fails, or finds too little confident text.
    """
    exe = tesseract_path()
    if not exe or not image_bytes:
        return ""
    try:
        proc = subprocess.run(
            [exe, "stdin", "stdout", "-l", lang, "--psm", "3", "tsv"],
            input=image_bytes,
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return _confident_text(proc.stdout.decode("utf-8", errors="replace"))


def _confident_text(tsv: str) -> str:
    """Rebuild text from Tesseract TSV, keeping only confident words."""
    lines: dict[tuple, list[str]] = {}
    order: list[tuple] = []
    confident = 0
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        word = (row.get("text") or "").strip()
        try:
            conf = float(row.get("conf") or -1)
        except ValueError:
            conf = -1
        if not word or conf < MIN_WORD_CONFIDENCE:
            continue
        key = (row.get("block_num"), row.get("par_num"), row.get("line_num"))
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(word)
        if any(c.isalnum() for c in word):
            confident += 1
    if confident < MIN_CONFIDENT_WORDS:
        return ""
    return "\n".join(" ".join(lines[k]) for k in order)
