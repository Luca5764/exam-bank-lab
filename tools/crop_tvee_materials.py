#!/usr/bin/env python3
"""
Crop visual materials (charts / figures) from TVE question PDFs.

This is a prototype companion to crop_tvee_questions.py. It first reuses the
full-question crop bounds, then looks for PDF vector drawings inside that
question and crops only the visual cluster instead of the whole question.

Example:
  python tools/crop_tvee_materials.py --year 110 --questions 26 31 --out .tmp/tvee_110_materials
"""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from crop_tvee_questions import DEFAULT_SOURCE_DIR, crop_questions, find_question_pdf, load_fitz


@dataclass
class MaterialCrop:
    id: int
    page: int
    image: str
    clip: list[float]
    source_clip: list[float]
    warnings: list[str]


def intersects(a: Any, b: Any) -> bool:
    return not (a.x1 <= b.x0 or a.x0 >= b.x1 or a.y1 <= b.y0 or a.y0 >= b.y1)


def union_rect(fitz: Any, rects: list[Any]) -> Any | None:
    if not rects:
        return None
    merged = fitz.Rect(rects[0])
    for rect in rects[1:]:
        merged |= rect
    return merged


def largest_drawing_cluster(fitz: Any, rects: list[Any], gap: float = 4) -> Any | None:
    clusters: list[list[Any]] = []
    for rect in rects:
        inflated = fitz.Rect(rect.x0 - gap, rect.y0 - gap, rect.x1 + gap, rect.y1 + gap)
        matches = [idx for idx, cluster in enumerate(clusters) if any(intersects(inflated, other) for other in cluster)]
        if not matches:
            clusters.append([rect])
            continue

        target = matches[0]
        clusters[target].append(rect)
        for idx in reversed(matches[1:]):
            clusters[target].extend(clusters.pop(idx))

    cluster_rects = [union_rect(fitz, cluster) for cluster in clusters]
    cluster_rects = [rect for rect in cluster_rects if rect is not None]
    if not cluster_rects:
        return None
    return max(cluster_rects, key=lambda rect: rect.width * rect.height)


def expand_rect(fitz: Any, rect: Any, page_rect: Any, margin: float) -> Any:
    return fitz.Rect(
        max(page_rect.x0, rect.x0 - margin),
        max(page_rect.y0, rect.y0 - margin),
        min(page_rect.x1, rect.x1 + margin),
        min(page_rect.y1, rect.y1 + margin),
    )


def expand_material_rect(fitz: Any, rect: Any, page_rect: Any, margin: float) -> Any:
    top_margin = min(margin, 1)
    return fitz.Rect(
        max(page_rect.x0, rect.x0 - margin),
        max(page_rect.y0, rect.y0 - top_margin),
        min(page_rect.x1, rect.x1 + margin),
        min(page_rect.y1, rect.y1 + margin),
    )


def drawing_rects_for_question(page: Any, question_clip: Any) -> list[Any]:
    rects = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None or rect.is_empty or rect.is_infinite:
            continue
        if not intersects(rect, question_clip):
            continue

        # Ignore tiny marks unless they are part of a larger visual cluster.
        if rect.width < 0.8 and rect.height < 0.8:
            continue
        rects.append(rect)
    return rects


def is_material_label(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    if len(cleaned) > 8:
        return False
    if any(ch in cleaned for ch in "，。！？；：、"):
        return False
    if re.search(r"[\u4e00-\u9fff]", cleaned) and len(cleaned) > 4:
        return False
    return True


def nearby_word_rects(page: Any, fitz: Any, visual_rect: Any, question_clip: Any, distance: float) -> list[Any]:
    x_distance = max(distance, 50)
    search_rect = fitz.Rect(
        max(question_clip.x0, visual_rect.x0 - x_distance),
        max(question_clip.y0, visual_rect.y0 - min(distance, 18)),
        min(question_clip.x1, visual_rect.x1 + x_distance),
        min(question_clip.y1, visual_rect.y1 + min(distance, 16)),
    )
    rects = []
    for word in page.get_text("words", clip=question_clip):
        if not is_material_label(word[4]):
            continue
        rect = fitz.Rect(word[:4])
        center = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
        if search_rect.contains(fitz.Point(*center)):
            rects.append(rect)
    return rects


def crop_materials(
    pdf_path: Path,
    out_dir: Path,
    qids: set[int] | None,
    dpi: int,
    margin: float,
    text_distance: float,
) -> list[MaterialCrop]:
    fitz = load_fitz()
    out_dir.mkdir(parents=True, exist_ok=True)
    image_dir = out_dir / "images"
    image_dir.mkdir(exist_ok=True)

    question_crops = crop_questions(
        pdf_path=pdf_path,
        out_dir=out_dir / "question_crops",
        dpi=dpi,
        x_margin=10,
        top_margin=8,
        bottom_gap=8,
    )

    crops: list[MaterialCrop] = []
    with fitz.open(str(pdf_path)) as doc:
        for question_crop in question_crops:
            if qids and question_crop.id not in qids:
                continue
            if not question_crop.clip or question_crop.page <= 0:
                continue

            page = doc[question_crop.page - 1]
            question_clip = fitz.Rect(question_crop.clip)
            drawings = drawing_rects_for_question(page, question_clip)
            visual_rect = largest_drawing_cluster(fitz, drawings)
            warnings: list[str] = []
            if visual_rect is None:
                crops.append(MaterialCrop(
                    id=question_crop.id,
                    page=question_crop.page,
                    image="",
                    clip=[],
                    source_clip=question_crop.clip,
                    warnings=["no vector drawing found inside question crop"],
                ))
                continue

            words = nearby_word_rects(page, fitz, visual_rect, question_clip, text_distance)
            material_rect = union_rect(fitz, [visual_rect, *words]) or visual_rect
            material_rect = expand_material_rect(fitz, material_rect, page.rect, margin)
            material_rect &= question_clip

            if material_rect.width < 24 or material_rect.height < 24:
                warnings.append("material crop is unusually small")
            if material_rect.width > question_clip.width * 0.85 or material_rect.height > question_clip.height * 0.85:
                warnings.append("material crop may still include too much question text")

            zoom = dpi / 72
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=material_rect, alpha=False)
            rel_image = f"images/q{question_crop.id:02d}.png"
            pix.save(out_dir / rel_image)

            crops.append(MaterialCrop(
                id=question_crop.id,
                page=question_crop.page,
                image=rel_image,
                clip=[round(material_rect.x0, 2), round(material_rect.y0, 2), round(material_rect.x1, 2), round(material_rect.y1, 2)],
                source_clip=question_crop.clip,
                warnings=warnings,
            ))

    return crops


def write_preview_html(out_dir: Path, year: str, crops: list[MaterialCrop]) -> None:
    cards = []
    for crop in crops:
        warning_html = "".join(f"<li>{html.escape(w)}</li>" for w in crop.warnings)
        cards.append(f"""
<section class="card {'warn' if crop.warnings else ''}">
  <h2>Q{crop.id:02d} <small>page {crop.page or '?'}</small></h2>
  {'<ul class="warnings">' + warning_html + '</ul>' if warning_html else ''}
  <p><strong>Material clip:</strong> {html.escape(str(crop.clip))}</p>
  {'<img src="' + html.escape(crop.image) + '" alt="Q' + str(crop.id) + ' material">' if crop.image else '<div class="missing">missing</div>'}
</section>
""")

    page = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TVE {html.escape(year)} Material Crop Preview</title>
  <style>
    body {{ font-family: "Noto Sans TC", "Microsoft JhengHei", sans-serif; margin: 24px; background: #f6f5ef; color: #1f1f1f; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 18px; }}
    .card {{ background: white; border: 1px solid #d5d0c5; border-radius: 14px; padding: 14px; }}
    .card.warn {{ border-color: #d99000; }}
    h1 {{ margin-bottom: 4px; }}
    h2 {{ margin: 0 0 8px; font-size: 18px; }}
    small {{ color: #666; font-weight: 400; }}
    p {{ color: #555; font-size: 13px; line-height: 1.5; }}
    img {{ display: block; max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 8px; background: white; }}
    .warnings {{ color: #a35b00; font-size: 14px; }}
    .missing {{ padding: 24px; border: 1px dashed #aaa; color: #777; }}
  </style>
</head>
<body>
  <h1>TVE {html.escape(year)} Material Crop Preview</h1>
  <div class="grid">
    {''.join(cards)}
  </div>
</body>
</html>
"""
    (out_dir / "preview.html").write_text(page, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Crop visual material images from TVE PDFs.")
    parser.add_argument("--year", required=True, help="Exam year, e.g. 110.")
    parser.add_argument("--source-dir", type=Path, default=Path(DEFAULT_SOURCE_DIR), help="TVE source root.")
    parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    parser.add_argument("--questions", type=int, nargs="*", help="Optional question ids to crop.")
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--margin", type=float, default=8)
    parser.add_argument("--text-distance", type=float, default=28)
    args = parser.parse_args()

    pdf_path = find_question_pdf(args.source_dir, args.year)
    crops = crop_materials(
        pdf_path=pdf_path,
        out_dir=args.out,
        qids=set(args.questions) if args.questions else None,
        dpi=args.dpi,
        margin=args.margin,
        text_distance=args.text_distance,
    )

    manifest = {
        "year": args.year,
        "source_pdf": str(pdf_path),
        "count": len([c for c in crops if c.image]),
        "materials": [asdict(c) for c in crops],
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_preview_html(args.out, args.year, crops)

    print(f"Cropped {manifest['count']} material images to {args.out}")
    print(f"Preview: {args.out / 'preview.html'}")
    for crop in crops:
        if crop.warnings:
            print(f"  Q{crop.id:02d}: {crop.warnings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
