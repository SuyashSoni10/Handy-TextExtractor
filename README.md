# extract_text.py — Image & PDF Text Extractor

Extract human-readable text from images and PDFs using Claude's vision AI.  
Tables are reconstructed as Markdown. Graphs and diagrams are skipped.

---

## Requirements

```bash
pip install anthropic pymupdf pillow
```

You also need an **Anthropic API key** set as an environment variable:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Usage

```bash
python extract_text.py <file_or_dir> [<file_or_dir> ...] [-o OUTPUT]
```

### Examples

```bash
# Single image
python extract_text.py scan.png

# Single PDF (all pages)
python extract_text.py report.pdf

# Multiple images
python extract_text.py page1.jpg page2.jpg page3.png

# A directory of images/PDFs
python extract_text.py ./scans/

# Custom output path
python extract_text.py invoice.pdf -o invoice_text
```

---

## Output format

| Content found         | Output format |
|-----------------------|---------------|
| Plain text only       | `.txt`        |
| Tables, headings, or  | `.md`         |
| structured content    |               |

The output format is chosen **automatically** based on what Claude detects.  
If you pass `-o myfile`, the correct extension (`.txt` or `.md`) is appended.

---

## Supported input formats

Images: `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif`  
Documents: `.pdf` (each page rendered at 150 DPI)

---

## How it works

1. **PDF pages** are rasterised to PNG images (150 DPI) via PyMuPDF.
2. Each image is sent to **Claude** with a strict OCR prompt.
3. Claude returns structured text — plain paragraphs, Markdown tables, headings, and lists — while ignoring charts and decorative graphics.
4. All pages/images are assembled into one output file.
   - Multi-page output uses section headers so you know which page each block came from.

---

## Notes

- Large images are automatically resized to keep API costs reasonable.
- If a page contains only a chart/graph, a placeholder comment is inserted: `<!-- [non-text figure omitted] -->`.
- Processing speed depends on the number of pages and Claude API response times.
