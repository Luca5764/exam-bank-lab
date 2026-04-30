#!/usr/bin/env python3
"""
Crop full-question screenshots from TVE joint entrance exam PDFs.

The crop is deterministic: locate question-number text coordinates in the PDF,
then crop from each question marker to the next marker on the same page. This
keeps charts and images intact without asking a model to choose the crop box.

Example:
  .venv\\Scripts\\python.exe tools\\crop_tvee_questions.py --year 114 --out C:\\tmp\\tvee_114_crops
"""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


QUESTION_PDF_SUFFIX = "\u984c.pdf"
DEFAULT_SOURCE_DIR = "\u7d71\u6e2c\u5c08\u4e8c"


@dataclass
class QuestionCrop:
    id: int
    page: int
    image: str
    clip: list[float]
    text_preview: str
    warnings: list[str]


def load_fitz() -> Any:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Missing dependency: install PyMuPDF first, e.g. `pip install PyMuPDF`.") from exc
    return fitz


def find_question_pdf(source_dir: Path, year: str) -> Path:
    year_dir = source_dir / year
    if not year_dir.exists():
        raise FileNotFoundError(f"Year directory not found: {year_dir}")
    matches = [p for p in year_dir.glob("*.pdf") if p.name.endswith(QUESTION_PDF_SUFFIX)]
    if len(matches) != 1:
        names = ", ".join(p.name for p in matches) or "(none)"
        raise FileNotFoundError(f"Expected exactly one question PDF in {year_dir}; found {names}")
    return matches[0]


def parse_marker(text: str) -> int | None:
    match = re.fullmatch(r"(\d{1,2})[.．]", text.strip())
    if not match:
        return None
    qid = int(match.group(1))
    return qid if 1 <= qid <= 50 else None


def collect_markers(doc: Any) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for page_index, page in enumerate(doc):
        for word in page.get_text("words"):
            qid = parse_marker(word[4])
            if qid is None:
                continue
            markers.append({
                "id": qid,
                "page_index": page_index,
                "x0": float(word[0]),
                "y0": float(word[1]),
                "x1": float(word[2]),
                "y1": float(word[3]),
            })

    # Keep the first occurrence for each id. The question PDF should have one
    # marker per id; this makes the tool robust against accidental duplicates.
    by_id: dict[int, dict[str, Any]] = {}
    for marker in sorted(markers, key=lambda m: (m["id"], m["page_index"], m["y0"], m["x0"])):
        by_id.setdefault(marker["id"], marker)
    return [by_id[qid] for qid in sorted(by_id)]


def text_preview(page: Any, clip: Any) -> str:
    text = page.get_text("text", clip=clip) or ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:220]


def crop_questions(
    pdf_path: Path,
    out_dir: Path,
    dpi: int,
    x_margin: float,
    top_margin: float,
    bottom_gap: float,
) -> list[QuestionCrop]:
    fitz = load_fitz()
    out_dir.mkdir(parents=True, exist_ok=True)
    image_dir = out_dir / "images"
    image_dir.mkdir(exist_ok=True)

    crops: list[QuestionCrop] = []
    with fitz.open(str(pdf_path)) as doc:
        markers = collect_markers(doc)
        marker_by_id = {m["id"]: m for m in markers}

        for qid in range(1, 51):
            marker = marker_by_id.get(qid)
            if not marker:
                crops.append(QuestionCrop(
                    id=qid,
                    page=0,
                    image="",
                    clip=[],
                    text_preview="",
                    warnings=["question marker not found"],
                ))
                continue

            page = doc[marker["page_index"]]
            page_rect = page.rect
            next_marker = marker_by_id.get(qid + 1)
            same_page_next = next_marker and next_marker["page_index"] == marker["page_index"]

            x0 = max(0, min(marker["x0"] - x_margin, 48))
            y0 = max(0, marker["y0"] - top_margin)
            x1 = min(page_rect.width, page_rect.width - 48)
            y1 = (next_marker["y0"] - bottom_gap) if same_page_next else (page_rect.height - 36)
            y1 = min(page_rect.height, max(y0 + 24, y1))

            clip = fitz.Rect(x0, y0, x1, y1)
            zoom = dpi / 72
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
            rel_image = f"images/q{qid:02d}.png"
            pix.save(out_dir / rel_image)

            warnings: list[str] = []
            if not same_page_next and qid < 50:
                warnings.append("next question is on another page; crop extends to page bottom")
            if clip.height < 60:
                warnings.append("crop is unusually short")

            crops.append(QuestionCrop(
                id=qid,
                page=marker["page_index"] + 1,
                image=rel_image,
                clip=[round(clip.x0, 2), round(clip.y0, 2), round(clip.x1, 2), round(clip.y1, 2)],
                text_preview=text_preview(page, clip),
                warnings=warnings,
            ))

    return crops


def write_preview_html(out_dir: Path, year: str, pdf_path: Path, crops: list[QuestionCrop]) -> None:
    cards = []
    for crop in crops:
        warning_html = "".join(f"<li>{html.escape(w)}</li>" for w in crop.warnings)
        cards.append(f"""
<section class="card {'warn' if crop.warnings else ''}">
  <h2>Q{crop.id:02d} <small>page {crop.page or '?'}</small></h2>
  {'<ul class="warnings">' + warning_html + '</ul>' if warning_html else ''}
  <p>{html.escape(crop.text_preview)}</p>
  {'<img src="' + html.escape(crop.image) + '" alt="Q' + str(crop.id) + '">' if crop.image else '<div class="missing">missing</div>'}
</section>
""")

    page = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TVE {html.escape(year)} Crop Preview</title>
  <style>
    body {{ font-family: "Noto Sans TC", "Microsoft JhengHei", sans-serif; margin: 24px; background: #f6f5ef; color: #1f1f1f; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 18px; }}
    .card {{ background: white; border: 1px solid #d5d0c5; border-radius: 14px; padding: 14px; }}
    .card.warn {{ border-color: #d99000; }}
    h1 {{ margin-bottom: 4px; }}
    h2 {{ margin: 0 0 8px; font-size: 18px; }}
    small {{ color: #666; font-weight: 400; }}
    p {{ color: #555; font-size: 14px; line-height: 1.6; }}
    img {{ display: block; max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 8px; background: white; }}
    .warnings {{ color: #a35b00; font-size: 14px; }}
    .missing {{ padding: 24px; border: 1px dashed #aaa; color: #777; }}
  </style>
</head>
<body>
  <h1>TVE {html.escape(year)} Crop Preview</h1>
  <p>Source: {html.escape(str(pdf_path))}</p>
  <div class="grid">
    {''.join(cards)}
  </div>
</body>
</html>
"""
    (out_dir / "preview.html").write_text(page, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Crop full-question screenshots from TVE PDFs.")
    parser.add_argument("--year", required=True, help="Exam year, e.g. 114.")
    parser.add_argument("--source-dir", type=Path, default=Path(DEFAULT_SOURCE_DIR), help="TVE source root.")
    parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    parser.add_argument("--dpi", type=int, default=180, help="Rendered image DPI.")
    parser.add_argument("--x-margin", type=float, default=10, help="Left margin before question marker.")
    parser.add_argument("--top-margin", type=float, default=8, help="Top margin before question marker.")
    parser.add_argument("--bottom-gap", type=float, default=8, help="Gap before next question marker.")
    args = parser.parse_args()

    pdf_path = find_question_pdf(args.source_dir, args.year)
    crops = crop_questions(
        pdf_path=pdf_path,
        out_dir=args.out,
        dpi=args.dpi,
        x_margin=args.x_margin,
        top_margin=args.top_margin,
        bottom_gap=args.bottom_gap,
    )

    manifest = {
        "year": args.year,
        "source_pdf": str(pdf_path),
        "count": len([c for c in crops if c.image]),
        "questions": [asdict(c) for c in crops],
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_preview_html(args.out, args.year, pdf_path, crops)

    missing = [c.id for c in crops if not c.image]
    warned = [c.id for c in crops if c.warnings]
    print(f"Cropped {manifest['count']} questions to {args.out}")
    print(f"Preview: {args.out / 'preview.html'}")
    if missing:
        print(f"Missing markers: {missing}")
    if warned:
        print(f"Warnings: {warned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
