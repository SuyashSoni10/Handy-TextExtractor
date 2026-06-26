# main.py — Image & PDF Text Extractor

Extract human-readable text from images and PDFs using Llama 3.1 vision via Groq.  
Tables are reconstructed as Markdown. Graphs and diagrams are skipped.

---

## Requirements

```bash
pip install openai pymupdf pillow python-dotenv
```

---

## API key setup

Create a `.env` file in the **same folder as the script**:

```
GROQ_API_KEY=gsk_...
```

The script loads it automatically on startup — no need to set environment variables manually.

---

## Usage

```bash
python main.py <file_or_dir> [<file_or_dir> ...] [OUTPUT_NAME] [-o OUTPUT]
```

### Examples

```bash
# Single image
python main.py scan.png

# Single PDF (all pages)
python main.py report.pdf

# Multiple images
python main.py page1.jpg page2.jpg page3.png

# A directory of images/PDFs
python main.py ./scans/

# A directory of images/PDFs with a custom output filename
python main.py ./scans/ my-desired-filename

# Custom output path
python main.py invoice.pdf -o invoice_text
```

---

## Output format

| Content found                      | Output format |
|------------------------------------|---------------|
| Plain text only                    | `.txt`        |
| Tables, headings, or structured content | `.md`    |

The output format is chosen **automatically** based on what the model detects.  
If you pass `-o myfile`, the correct extension (`.txt` or `.md`) is appended.

---

## Supported input formats

Images: `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.dng` 
Documents: `.pdf` (each page rendered at 150 DPI)

---

## How it works

1. **PDF pages** are rasterised to PNG images (150 DPI) via PyMuPDF.
2. Each image is sent to **Llama 3.1 8B** (via Groq) with a strict OCR prompt.
3. The model returns structured text — plain paragraphs, Markdown tables, headings, and lists — while ignoring charts and decorative graphics.
4. All pages/images are assembled into one output file.
   - Multi-page output uses section headers so you know which page each block came from.

---

## Notes

- Large images are automatically resized to keep API costs reasonable.
- If a page contains only a chart/graph, a placeholder comment is inserted: `<!-- [non-text figure omitted] -->`.
- Processing speed depends on the number of pages and Groq API response times.
