"""REK-1 XML generator for eDavki.

Generates a simplified REK-1 XML structure. The official eDavki schema
(http://edavki.durs.si/Documents/Schemas/REK_1_2.xsd) requires an
authenticated submission — this produces the file for manual upload.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, indent, tostring
from typing import Any

import src.database as db

EXPORTS_DIR = Path(__file__).parent.parent.parent / "exports"


def _text(parent: Element, tag: str, text: str | None) -> Element:
    el = SubElement(parent, tag)
    el.text = text or ""
    return el


async def build_rek1_xml(period_month: int, period_year: int) -> Path:
    """Generate REK-1 XML for a given month/year and save to exports/."""
    rows = await db.fetch(
        """
        SELECT
            pr.*,
            e.first_name, e.last_name, e.emso, e.davcna_stevilka, e.tax_card
        FROM payroll_runs pr
        JOIN employees e ON e.id = pr.employee_id
        WHERE pr.period_month = $1 AND pr.period_year = $2
          AND pr.status IN ('calculated', 'confirmed', 'paid')
        ORDER BY e.last_name, e.first_name
        """,
        period_month, period_year,
    )

    root = Element(
        "DDDIF",
        attrib={"xmlns": "http://edavki.durs.si/Documents/Schemas/REK_1_2.xsd"},
    )

    header = SubElement(root, "Header")
    _text(header, "Period", f"{period_year}-{period_month:02d}")
    _text(header, "FormType", "REK-1")
    _text(header, "Created", date.today().isoformat())
    _text(header, "RecordCount", str(len(rows)))

    record_set = SubElement(root, "RecordSet")

    for row in rows:
        record = SubElement(record_set, "Record")

        emp_el = SubElement(record, "Employee")
        _text(emp_el, "EMSO", row["emso"] or "")
        _text(emp_el, "TaxId", row["davcna_stevilka"] or "")
        _text(emp_el, "FirstName", row["first_name"])
        _text(emp_el, "LastName", row["last_name"])

        payroll_el = SubElement(record, "Payroll")
        _text(payroll_el, "GrossSalary", str(round(float(row["gross_salary"] or 0), 2)))
        _text(payroll_el, "NetSalary", str(round(float(row["net_salary"] or 0), 2)))

        contrib_el = SubElement(record, "Contributions")
        _text(contrib_el, "EmployeeContributions",
              str(round(float(row["employee_contributions"] or 0), 2)))
        _text(contrib_el, "EmployerContributions",
              str(round(float(row["employer_contributions"] or 0), 2)))
        _text(contrib_el, "IncomeTax",
              str(round(float(row["income_tax"] or 0), 2)))

    indent(root, space="  ")
    xml_bytes = tostring(root, encoding="unicode", xml_declaration=False)
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes

    EXPORTS_DIR.mkdir(exist_ok=True)
    out_path = EXPORTS_DIR / f"REK-1_{period_year}-{period_month:02d}.xml"
    out_path.write_text(xml_content, encoding="utf-8")

    # Mark all included runs as rek1_exported
    await db.execute(
        """
        UPDATE payroll_runs
        SET rek1_exported = TRUE
        WHERE period_month = $1 AND period_year = $2
          AND status IN ('calculated', 'confirmed', 'paid')
        """,
        period_month, period_year,
    )

    return out_path
