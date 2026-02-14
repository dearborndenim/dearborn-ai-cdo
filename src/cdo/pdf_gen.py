"""
Tech Pack PDF Generator

Generates downloadable PDF tech packs with:
- Product info and sketch
- Size specification table
- Bill of materials with costs
- Construction operations with sewing times
- Total cost breakdown
"""
import io
import logging
from typing import Optional

from fpdf import FPDF
from sqlalchemy.orm import Session

from ..db import TechPack, TechPackMeasurement, TechPackMaterial, TechPackConstruction

logger = logging.getLogger(__name__)

LABOR_RATE_PER_HOUR = 26.00  # $17/hr base x 1.5 fully loaded


class TechPackPDF(FPDF):
    """Custom FPDF class for tech pack documents."""

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, "DEARBORN DENIM & APPAREL", align="C")
        self.ln(5)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, "Technical Specification Package", align="C")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}} | Confidential", align="C")

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 11)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 8, f"  {title}", fill=True)
        self.ln(10)

    def table_header(self, headers: list, widths: list):
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(50, 50, 80)
        self.set_text_color(255, 255, 255)
        for header, width in zip(headers, widths):
            self.cell(width, 7, header, border=1, fill=True, align="C")
        self.ln()
        self.set_text_color(0, 0, 0)

    def table_row(self, cells: list, widths: list, fill: bool = False):
        self.set_font("Helvetica", "", 7)
        if fill:
            self.set_fill_color(248, 248, 252)
        for cell, width in zip(cells, widths):
            self.cell(width, 6, str(cell), border=1, fill=fill, align="C")
        self.ln()


def generate_tech_pack_pdf(db: Session, tech_pack_id: int) -> Optional[bytes]:
    """Generate a PDF for a tech pack."""
    tech_pack = db.query(TechPack).filter(TechPack.id == tech_pack_id).first()
    if not tech_pack:
        return None

    measurements = sorted(tech_pack.measurements, key=lambda m: m.size)
    materials = list(tech_pack.materials)
    construction = sorted(tech_pack.construction, key=lambda c: c.operation_number)

    pdf = TechPackPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    # --- Product Info ---
    pdf.section_title("PRODUCT INFORMATION")
    pdf.set_font("Helvetica", "", 9)
    info = [
        ("Tech Pack #", tech_pack.tech_pack_number),
        ("Style Name", tech_pack.style_name or ""),
        ("Category", (tech_pack.category or "").replace("_", " ").title()),
        ("Season", tech_pack.season or ""),
        ("Status", (tech_pack.status.value if tech_pack.status else "draft").title()),
    ]
    if tech_pack.fit_type:
        info.append(("Fit Type", tech_pack.fit_type))
    if tech_pack.primary_fabric:
        info.append(("Primary Fabric", tech_pack.primary_fabric))

    for label, value in info:
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(40, 6, label + ":")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 6, str(value))
        pdf.ln()

    if tech_pack.description:
        pdf.ln(3)
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 5, tech_pack.description[:500])

    pdf.ln(5)

    # --- Cost Summary ---
    pdf.section_title("COST SUMMARY")
    material_total = sum((m.unit_cost or 0) * (m.quantity_per_unit or 0) for m in materials)
    total_sewing_minutes = sum(getattr(c, "estimated_minutes", 0) or 0 for c in construction)
    labor_cost = (total_sewing_minutes / 60) * LABOR_RATE_PER_HOUR
    total_cost = material_total + labor_cost

    cost_info = [
        ("Material Cost", f"${material_total:.2f}"),
        ("Labor Cost", f"${labor_cost:.2f} ({total_sewing_minutes} min @ ${LABOR_RATE_PER_HOUR:.2f}/hr)"),
        ("Total Manufacturing Cost", f"${total_cost:.2f}"),
    ]
    if tech_pack.target_retail:
        margin = ((tech_pack.target_retail - total_cost) / tech_pack.target_retail * 100)
        cost_info.append(("Target Retail", f"${tech_pack.target_retail:.2f}"))
        cost_info.append(("Estimated Margin", f"{margin:.1f}%"))

    for label, value in cost_info:
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(50, 6, label + ":")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 6, str(value))
        pdf.ln()

    pdf.ln(5)

    # --- Size Spec Table ---
    if measurements:
        pdf.section_title("SIZE SPECIFICATIONS (inches)")
        headers = ["Size", "Waist", "F.Rise", "B.Rise", "Hip", "Thigh", "Knee", "Leg Op.", "Inseam", "Outseam"]
        widths = [18, 18, 18, 18, 18, 18, 18, 18, 18, 18]

        pdf.table_header(headers, widths)

        for i, m in enumerate(measurements):
            cells = [
                m.size,
                f"{m.waist:.1f}" if m.waist else "-",
                f"{m.front_rise:.1f}" if m.front_rise else "-",
                f"{m.back_rise:.1f}" if m.back_rise else "-",
                f"{m.hip:.1f}" if m.hip else "-",
                f"{m.thigh:.1f}" if m.thigh else "-",
                f"{m.knee:.1f}" if m.knee else "-",
                f"{m.leg_opening:.1f}" if m.leg_opening else "-",
                f"{m.inseam:.1f}" if m.inseam else "-",
                f"{m.outseam:.1f}" if m.outseam else "-",
            ]
            pdf.table_row(cells, widths, fill=(i % 2 == 0))

        pdf.ln(5)

    # --- Bill of Materials ---
    if materials:
        pdf.section_title("BILL OF MATERIALS")
        headers = ["Type", "Material", "Placement", "Qty", "Unit", "Unit Cost", "Total"]
        widths = [22, 40, 30, 16, 16, 22, 22]

        pdf.table_header(headers, widths)

        for i, m in enumerate(materials):
            qty = m.quantity_per_unit or 0
            cost = m.unit_cost or 0
            cells = [
                (m.material_type or "").title(),
                m.material_name or "",
                m.placement or "",
                f"{qty:.2f}" if qty else "-",
                m.unit_of_measure or "",
                f"${cost:.2f}" if cost else "-",
                f"${qty * cost:.2f}" if qty and cost else "-",
            ]
            pdf.table_row(cells, widths, fill=(i % 2 == 0))

        # Total row
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(sum(widths[:-1]), 7, "TOTAL MATERIAL COST", border=1, align="R")
        pdf.cell(widths[-1], 7, f"${material_total:.2f}", border=1, align="C")
        pdf.ln(8)

    # --- Construction Operations ---
    if construction:
        pdf.section_title("CONSTRUCTION OPERATIONS")
        headers = ["#", "Operation", "Description", "Machine", "Stitch", "Est. Min"]
        widths = [10, 30, 50, 30, 18, 18]

        pdf.table_header(headers, widths)

        for i, c in enumerate(construction):
            est_min = getattr(c, "estimated_minutes", None) or ""
            cells = [
                str(c.operation_number),
                c.operation_name or "",
                (c.description or "")[:60],
                c.machine_type or "-",
                c.stitch_type or "-",
                str(est_min) if est_min else "-",
            ]
            pdf.table_row(cells, widths, fill=(i % 2 == 0))

        # Total row
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(sum(widths[:-1]), 7, "TOTAL SEWING TIME", border=1, align="R")
        pdf.cell(widths[-1], 7, f"{total_sewing_minutes} min", border=1, align="C")
        pdf.ln()

    # Output to bytes
    return bytes(pdf.output())
