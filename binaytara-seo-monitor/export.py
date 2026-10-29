"""
Binaytara SEO Monitor — Excel Export
Generates formatted .xlsx files from DataFrames.
"""

import io
from datetime import datetime
import pandas as pd
from config import BRAND_NAVY


def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Data",
                   metadata: str = "") -> bytes:
    """
    Convert a DataFrame to a formatted Excel file in memory.
    Returns bytes suitable for st.download_button.
    """
    buf = io.BytesIO()

    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        # Write metadata row first, then the data starting at row 2
        start_row = 2 if metadata else 0
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=start_row)

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # ── Formats ──
        header_fmt = workbook.add_format({
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": BRAND_NAVY,
            "border": 1,
            "text_wrap": True,
            "valign": "vcenter",
        })
        meta_fmt = workbook.add_format({
            "italic": True,
            "font_color": "#666666",
            "font_size": 9,
        })
        num_fmt = workbook.add_format({"num_format": "#,##0"})
        pct_fmt = workbook.add_format({"num_format": "0.00%"})
        pos_fmt = workbook.add_format({"num_format": "0.0"})
        green_fmt = workbook.add_format({"font_color": "#1E7E34", "bg_color": "#E2EFDA"})
        red_fmt = workbook.add_format({"font_color": "#DC3545", "bg_color": "#FFF2CC"})

        # ── Metadata row ──
        if metadata:
            worksheet.merge_range(0, 0, 0, max(len(df.columns) - 1, 1), metadata, meta_fmt)

        # ── Header row ──
        for col_num, col_name in enumerate(df.columns):
            worksheet.write(start_row, col_num, col_name, header_fmt)

        # ── Column widths (auto-fit estimate) ──
        for col_num, col_name in enumerate(df.columns):
            max_len = max(
                len(str(col_name)),
                df[col_name].astype(str).str.len().max() if len(df) > 0 else 0,
            )
            worksheet.set_column(col_num, col_num, min(max_len + 4, 60))

        # ── Conditional formatting on "change" columns ──
        data_start_row = start_row + 1
        data_end_row = data_start_row + len(df) - 1
        if len(df) > 0:
            for col_num, col_name in enumerate(df.columns):
                col_lower = col_name.lower()
                if "change" in col_lower or "delta" in col_lower:
                    # For position change, reversed: negative = good
                    if "position" in col_lower:
                        worksheet.conditional_format(data_start_row, col_num, data_end_row, col_num, {
                            "type": "cell", "criteria": "<", "value": 0, "format": green_fmt,
                        })
                        worksheet.conditional_format(data_start_row, col_num, data_end_row, col_num, {
                            "type": "cell", "criteria": ">", "value": 0, "format": red_fmt,
                        })
                    else:
                        worksheet.conditional_format(data_start_row, col_num, data_end_row, col_num, {
                            "type": "cell", "criteria": ">", "value": 0, "format": green_fmt,
                        })
                        worksheet.conditional_format(data_start_row, col_num, data_end_row, col_num, {
                            "type": "cell", "criteria": "<", "value": 0, "format": red_fmt,
                        })

                # Number formatting
                if "ctr" in col_lower:
                    worksheet.set_column(col_num, col_num, 10, pct_fmt)
                elif "position" in col_lower:
                    worksheet.set_column(col_num, col_num, 10, pos_fmt)
                elif any(k in col_lower for k in ["users", "clicks", "impressions", "sessions", "views"]):
                    worksheet.set_column(col_num, col_num, 12, num_fmt)

        # Freeze header
        worksheet.freeze_panes(start_row + 1, 0)
        worksheet.autofilter(start_row, 0, data_end_row if len(df) > 0 else start_row, len(df.columns) - 1)

    return buf.getvalue()


def make_filename(prefix: str, start: str, end: str, page_slug: str = "") -> str:
    """Build a descriptive filename for the export."""
    parts = ["binaytara", prefix]
    if page_slug:
        # Clean the slug: take last path segment, truncate
        slug = page_slug.rstrip("/").split("/")[-1][:50]
        if slug:
            parts.append(slug)
    parts.extend([start, end])
    return "_".join(parts) + ".xlsx"


def multi_sheet_export(sheets: dict[str, pd.DataFrame], metadata: str = "") -> bytes:
    """
    Export multiple DataFrames into one Excel file with multiple sheets.
    sheets: {"Sheet Name": DataFrame, ...}
    """
    buf = io.BytesIO()

    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        workbook = writer.book
        header_fmt = workbook.add_format({
            "bold": True, "font_color": "#FFFFFF",
            "bg_color": BRAND_NAVY, "border": 1, "text_wrap": True,
        })
        meta_fmt = workbook.add_format({"italic": True, "font_color": "#666666", "font_size": 9})

        for sheet_name, df in sheets.items():
            start_row = 2 if metadata else 0
            # Truncate sheet name to Excel limit
            safe_name = sheet_name[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False, startrow=start_row)
            ws = writer.sheets[safe_name]

            if metadata:
                ws.merge_range(0, 0, 0, max(len(df.columns) - 1, 1), metadata, meta_fmt)

            for col_num, col_name in enumerate(df.columns):
                ws.write(start_row, col_num, col_name, header_fmt)
                max_len = max(len(str(col_name)), df[col_name].astype(str).str.len().max() if len(df) > 0 else 0)
                ws.set_column(col_num, col_num, min(max_len + 4, 60))

            ws.freeze_panes(start_row + 1, 0)

    return buf.getvalue()
