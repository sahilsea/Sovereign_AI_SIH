"""Deliverable files written by the agent's tools (harness/agent_tools.py).

Same stamping discipline as deliver/docx.py and deliver/pptx.py: every
Word/PowerPoint/Excel file the agent produces carries the classification
Label it inherited (from every corpus passage the agent had seen when it
wrote the file), in a banner AND in a running header/footer or per-slide
footer, so the marking survives the file leaving the workbench.
"""

from __future__ import annotations

import io
import re
from typing import Any, Sequence

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from pptx import Presentation
from pptx.dml.color import RGBColor as PptxRGBColor
from pptx.util import Inches, Pt as PptxPt

from contracts import Label, Tier
from deliver.docx import TIER_COLORS, _add_markdown_answer

_HEX = {Tier.SECRET: "B91C1C", Tier.CONFIDENTIAL: "C2410C", Tier.INTERNAL: "1D4ED8", Tier.PUBLIC: "047857"}


def banner_text(label: Label) -> str:
    tier = label.tier.value.upper()
    if label.compartments:
        comps = ", ".join(sorted(c.value.upper() for c in label.compartments))
        return f"CLASSIFICATION: {tier} // COMPARTMENTS: [{comps}]"
    return f"CLASSIFICATION: {tier} // UNRESTRICTED DISTRIBUTION"


def build_docx(title: str, markdown: str, label: Label) -> bytes:
    doc = Document()
    color = TIER_COLORS.get(label.tier, RGBColor(0, 0, 0))
    text = banner_text(label)
    for section in doc.sections:
        for part in (section.header, section.footer):
            p = part.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            run.bold = True
            run.font.size = Pt(8.5)
            run.font.color.rgb = color
    banner = doc.add_paragraph()
    banner.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = banner.add_run(f"*** {text} ***")
    run.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = color
    doc.add_heading(title or "Document", level=1)
    _add_markdown_answer(doc, _markdown_tables_to_text(markdown or ""))
    foot = doc.add_paragraph()
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = foot.add_run("Generated on-premise by the SEVERANCE agent. Review before approval.")
    run.italic = True
    run.font.size = Pt(8)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()


def _markdown_tables_to_text(md: str) -> str:
    """Word has no Markdown tables; turn '| a | b |' rows into '- a — b'."""
    out = []
    for line in md.split("\n"):
        stripped = line.strip()
        if re.match(r"^\|?\s*:?-{3,}", stripped):
            continue  # separator row
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            out.append("- " + " — ".join(c for c in cells if c))
        else:
            out.append(line)
    return "\n".join(out)


def build_pptx(title: str, slides: Sequence[dict[str, Any]], label: Label) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    rgb = PptxRGBColor.from_string(_HEX.get(label.tier, "000000"))
    text = banner_text(label)

    def footer(slide):
        box = slide.shapes.add_textbox(Inches(0.3), prs.slide_height - Inches(0.5), prs.slide_width - Inches(0.6), Inches(0.35))
        box.text_frame.text = text
        r = box.text_frame.paragraphs[0].runs[0]
        r.font.size, r.font.bold, r.font.color.rgb = PptxPt(10), True, rgb

    cover = prs.slides.add_slide(prs.slide_layouts[0])
    cover.shapes.title.text = title or "Presentation"
    cover.placeholders[1].text = text
    footer(cover)

    for spec in slides or []:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = str(spec.get("title", ""))[:120]
        body = slide.placeholders[1].text_frame
        bullets = spec.get("bullets") or spec.get("points") or []
        if isinstance(bullets, str):
            bullets = [b for b in bullets.split("\n") if b.strip()]
        for i, bullet in enumerate(bullets[:10]):
            para = body.paragraphs[0] if i == 0 else body.add_paragraph()
            para.text = str(bullet).lstrip("-• ").strip()[:300]
            para.font.size = PptxPt(20)
        footer(slide)

    bio = io.BytesIO()
    prs.save(bio)
    return bio.getvalue()


def _coerce(value: Any) -> Any:
    """Keep numbers numeric so Excel can compute on them."""
    if isinstance(value, (int, float)) or value is None:
        return value
    s = str(value).strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d*\.\d+", s):
        return float(s)
    return s


def build_xlsx(sheets: dict[str, Sequence[Sequence[Any]]], label: Label) -> bytes:
    """sheets: {sheet name: rows}; the first row of each sheet is bolded as a header."""
    wb = Workbook()
    wb.remove(wb.active)
    fill = PatternFill(start_color=_HEX.get(label.tier, "000000"), end_color=_HEX.get(label.tier, "000000"), fill_type="solid")
    for name, rows in (sheets or {"Sheet1": []}).items():
        ws = wb.create_sheet(title=re.sub(r"[\[\]:*?/\\]", "_", str(name))[:31] or "Sheet")
        ws.append([banner_text(label)])
        ws["A1"].font = Font(bold=True, color="FFFFFF")
        ws["A1"].fill = fill
        for r_idx, row in enumerate(rows or []):
            ws.append([_coerce(v) for v in (row if isinstance(row, (list, tuple)) else [row])])
            if r_idx == 0:
                for cell in ws[ws.max_row]:
                    cell.font = Font(bold=True)
        for col in ws.columns:
            width = max((len(str(c.value)) for c in col[1:] if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 8), 60)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
