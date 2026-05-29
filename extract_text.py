#!/usr/bin/env python3
"""
extract_text.py — Extract text from images and PDFs using Claude vision.

Usage:
    python extract_text.py <file_or_dir> [<file_or_dir> ...] [-o OUTPUT]

Supports:
    • Single image files  (.png, .jpg, .jpeg, .webp, .gif, .bmp, .tiff, .tif)
    • Multiple image files passed at once
    • PDF files (each page is rendered and sent to Claude)
    • A directory of images / PDFs

Output:
    • Plain .txt  — when every page contains only plain text
    • .md         — when any page has tables or structured content
"""

import argparse
import base64
import io
import mimetypes
import os
import re
import sys
import fitz
from pathlib import Path

from openai import OpenAI
from PIL import Image
from dotenv import load_dotenv
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# NOTE:
# PyMuPDF imports as `import fitz`. In your environment, importing `fitz`
# currently crashes due to an unrelated package named `fitz`/web UI being
# installed. To avoid that hard import-time failure, we import fitz lazily
# only when we actually process a PDF, and we fail with a clear message.



# ── configuration ──────────────────────────────────────────────────────────────

SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"}
PDF_DPI = 150           # rendering resolution for PDF pages
MAX_IMAGE_LONG_SIDE = 1568  # Claude's recommended max; keeps token cost down

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = """You are an expert OCR assistant. Your job is to extract all readable text from the image provided.

Rules:
- Preserve the original reading order and natural paragraph breaks.
- If there are headings, preserve them (e.g., use Markdown # / ## / ### headings).
- If there is a TABLE, reconstruct it as a Markdown table with the exact column headers and row values. Align columns properly.
- If there are bullet lists or numbered lists, preserve them using Markdown syntax.
- IGNORE graphs, charts, diagrams, logos, decorative images, and complex shapes — output nothing for those.
- Do NOT add commentary, explanations, or preamble. Output ONLY the extracted content.
- If a section contains ONLY a graph/chart/diagram and no readable text, output: <!-- [non-text figure omitted] -->
- Use plain UTF-8 text. No HTML tags except the comment above."""


# ── helpers ────────────────────────────────────────────────────────────────────

def resize_image_bytes(img_bytes: bytes, max_side: int = MAX_IMAGE_LONG_SIDE) -> bytes:
    """Resize image so its longest side ≤ max_side; return PNG bytes."""
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def image_to_b64(img_bytes: bytes) -> tuple[str, str]:
    """Return (base64_string, media_type)."""
    data = resize_image_bytes(img_bytes)
    return base64.standard_b64encode(data).decode("utf-8"), "image/png"


def pdf_page_to_image_bytes(page, dpi: int = PDF_DPI) -> bytes:
    """Rasterise a PDF page and return PNG bytes (PyMuPDF/fitz)."""
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError(
            "PyMuPDF import failed (import fitz). "
            "Your environment seems to have an incompatible third-party 'fitz' package installed. "
            "Fix by uninstalling the wrong package and installing PyMuPDF: "
            "`pip uninstall -y fitz && pip install PyMuPDF`. "
            f"Original error: {e}"
        )

    mat = fitz.Matrix(dpi / 72, dpi / 72)

    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")



def has_structure(text: str) -> bool:
    """Return True if the extracted text contains Markdown tables or headings."""
    return bool(re.search(r"^\s*\|.+\|", text, re.MULTILINE) or
                re.search(r"^\s*#{1,6} ", text, re.MULTILINE))


# ── Claude API call ────────────────────────────────────────────────────────────

def extract_from_image(client: OpenAI, img_bytes: bytes, label: str) -> str:
    """Send one image to Claude and return extracted text."""
    b64, media_type = image_to_b64(img_bytes)
    print(f"  → Processing {label} …", flush=True)
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{b64}"
                        },
                    },
                    {"type": "text", "text": "Extract all text from this image."},
                ],
            },
        ],
    )
    return response.choices[0].message.content.strip()


# ── file collectors ────────────────────────────────────────────────────────────

def collect_inputs(paths: list[str]) -> list[Path]:
    """Expand directories, validate extensions, return sorted Path list."""
    result: list[Path] = []
    for p in paths:
        fp = Path(p)
        if fp.is_dir():
            for child in sorted(fp.iterdir()):
                ext = child.suffix.lower()
                if ext in SUPPORTED_IMAGE_EXTS or ext == ".pdf":
                    result.append(child)
        elif fp.is_file():
            ext = fp.suffix.lower()
            if ext in SUPPORTED_IMAGE_EXTS or ext == ".pdf":
                result.append(fp)
            else:
                print(f"[warn] Skipping unsupported file: {fp}", file=sys.stderr)
        else:
            print(f"[warn] Path not found: {fp}", file=sys.stderr)
    return result


# ── processing ─────────────────────────────────────────────────────────────────

def process_file(client, filepath: Path) -> list[tuple[str, str]]:

    """
    Process one file (image or PDF).
    Returns list of (label, extracted_text) tuples — one per page/image.
    """
    ext = filepath.suffix.lower()
    results = []

    if ext == ".pdf":
        doc = fitz.open(str(filepath))
        n = len(doc)
        print(f"[pdf] {filepath.name}  ({n} page{'s' if n != 1 else ''})")
        for i, page in enumerate(doc, 1):
            label = f"{filepath.name} — page {i}/{n}"
            img_bytes = pdf_page_to_image_bytes(page)
            text = extract_from_image(client, img_bytes, label)
            results.append((label, text))
        doc.close()

    else:
        print(f"[img] {filepath.name}")
        img_bytes = filepath.read_bytes()
        text = extract_from_image(client, img_bytes, filepath.name)
        results.append((filepath.name, text))

    return results


# ── output assembly ────────────────────────────────────────────────────────────

def build_output(all_results: list[tuple[str, str]], source_count: int) -> tuple[str, str]:
    """
    Assemble final document.
    Returns (content_string, extension) where extension is 'txt' or 'md'.
    """
    needs_md = any(has_structure(text) for _, text in all_results)
    ext = "md" if needs_md else "txt"

    parts: list[str] = []

    if source_count > 1 or any("page" in label for label, _ in all_results):
        # Multi-source or multi-page: add section headers
        for label, text in all_results:
            if needs_md:
                parts.append(f"## {label}\n\n{text}")
            else:
                separator = f"{'─' * 60}\n{label}\n{'─' * 60}"
                parts.append(f"{separator}\n\n{text}")
    else:
        # Single image, plain output
        parts.append(all_results[0][1])

    joiner = "\n\n---\n\n" if needs_md else "\n\n\n"
    content = joiner.join(parts)

    if needs_md and source_count > 1:
        title = "# Extracted Content\n\n"
        content = title + content

    return content, ext


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract text from images/PDFs using Claude vision."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="FILE_OR_DIR",
        help="Image file(s), PDF file(s), or directory containing them.",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="OUTPUT",
        help="Output file path (extension auto-set to .txt or .md if omitted).",
    )
    args = parser.parse_args()

    # Collect and validate inputs
    files = collect_inputs(args.inputs)
    if not files:
        print("No supported files found.", file=sys.stderr)
        sys.exit(1)

    print(f"\nFound {len(files)} file(s) to process.\n")

    # Initialise client (reads ANTHROPIC_API_KEY from env)
    # try:
    #     client = anthropic.Anthropic()
    # except Exception as e:
    #     print(f"[error] Could not initialise Anthropic client: {e}", file=sys.stderr)
    #     sys.exit(1)
    try:
        client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    except Exception as e:
        print(f"[error] Could not initialise Groq client: {e}", file=sys.stderr)
        sys.exit(1)

    # Extract text
    all_results: list[tuple[str, str]] = []
    for fp in files:
        try:
            all_results.extend(process_file(client, fp))
        except Exception as e:
            print(f"[error] Failed to process {fp}: {e}", file=sys.stderr)

    if not all_results:
        print("No text could be extracted.", file=sys.stderr)
        sys.exit(1)

    # Build output
    content, ext = build_output(all_results, source_count=len(files))

    # Determine output path
    if args.output:
        out_path = Path(args.output)
        # Correct extension if user didn't specify one
        if out_path.suffix.lower() not in (".txt", ".md"):
            out_path = out_path.with_suffix(f".{ext}")
    else:
        # Derive from first input
        stem = files[0].stem if len(files) == 1 else "extracted"
        out_path = Path(stem).with_suffix(f".{ext}")

    out_path.write_text(content, encoding="utf-8")
    print(f"\n✓ Saved → {out_path}  ({ext.upper()} format)")


if __name__ == "__main__":
    main()
