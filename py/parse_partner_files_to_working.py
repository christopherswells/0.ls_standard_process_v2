# -*- coding: utf-8 -*-
"""
Created on Tue May 12 16:42:53 2026

@author: Chris.Wells

parse_district_data_files


"""

from pathlib import Path
import re
import shutil
import pandas as pd


# =========================
# Helpers
# =========================

def ensure_dirs(*dirs: Path) -> None:
    """Create directories if missing."""
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

def list_filenames_lower(directory: Path) -> set:
    """Return a set of filenames (lowercased) in directory (non-recursive)."""
    if not directory.exists():
        return set()
    return {p.name.lower() for p in directory.iterdir() if p.is_file()}

def read_any_file(path: Path) -> pd.DataFrame:
    """
    Read CSV/XLSX into a DataFrame.
    - Excel: reads the first sheet
    - dtype=str avoids dtype surprises
    """
    suffix = path.suffix.lower()

    if suffix == ".csv":
        # Try a few common encodings (district files can be inconsistent)
        for enc in ("utf-8-sig", "utf-8", "cp1252"):
            try:
                return pd.read_csv(path, dtype=str, encoding=enc)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(path, dtype=str, encoding_errors="replace")

    if suffix == ".xlsx":
        return pd.read_excel(path, dtype=str, sheet_name=0, engine="openpyxl")

    raise ValueError(f"Unsupported file type: {path.suffix} (supported: .csv, .xlsx)")

def write_any_file(df: pd.DataFrame, out_path: Path) -> Path:
    """Write DataFrame back as CSV/XLSX based on output extension."""
    suffix = out_path.suffix.lower()

    if suffix == ".csv":
        df.to_csv(out_path, index=False)
        return out_path

    if suffix == ".xlsx":
        # na_rep="" makes missing display as blank cells in Excel,
        # while still being missing in-memory.
        df.to_excel(out_path, index=False, engine="openpyxl", na_rep="")
        return out_path

    raise ValueError(f"Unsupported output type: {suffix} (supported: .csv, .xlsx)")

def extract_agency_code(filename: str) -> str | None:
    """
    NO FALLBACK.

    Only accept digits that are the final token immediately before the extension
    and are preceded by a separator (space/underscore/hyphen).

    Examples:
      'Newman Academy 17245.xlsx'  -> '17245'
      'District_17245.xlsx'        -> '17245'
      'District-17245.csv'         -> '17245'
      'District 17245 v2.xlsx'     -> None
      'District17245.xlsx'         -> None
      'District.xlsx'              -> None
    """
    m = re.search(r"(?:^|[ _-])(\d+)(?=\.(xlsx|csv)$)", filename, flags=re.IGNORECASE)
    return m.group(1) if m else None

def add_required_columns(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    """
    Add:
      - filenameFromDistrict (string)
      - agency_code (string dtype, missing if not parsed)
    """
    df2 = df.copy()
    df2["filenameFromDistrict"] = filename

    code = extract_agency_code(filename)

    # Make it truly "missing" if not present (not blank string).
    # Using pandas "string" dtype yields <NA> when code is None.
    df2["agency_code"] = pd.Series([code] * len(df2), dtype="string")

    return df2

def template_column_count(template_path: Path) -> int:
    """Read template and return number of columns."""
    tmpl_df = read_any_file(template_path)
    return tmpl_df.shape[1]


# =========================
# Main processing logic
# =========================

def process_original_files(template_cols: int) -> None:
    """
    ORIGINAL_FILES logic:
      - If filename exists in WORKING/REJECTED/EDITED -> skip
      - If col count matches template -> write to WORKING + add columns
      - Else -> copy to REJECTED
    """
    existing_elsewhere = (
        list_filenames_lower(WORKING_FILES)
        | list_filenames_lower(REJECTED_DIR)
        | list_filenames_lower(EDITED_DIR)
    )

    candidates = sorted([
        p for p in ORIGINAL_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".csv", ".xlsx")
    ])

    for src in candidates:
        if src.name.lower() in existing_elsewhere:
            print(f"SKIP (already in WORKING/REJECTED/EDITED): {src.name}")
            continue

        try:
            df = read_any_file(src)
        except Exception as e:
            print(f"REJECT (read error): {src.name} -> {e}")
            shutil.copy2(src, REJECTED_DIR / src.name)
            continue

        if df.shape[1] == template_cols:
            out_path = WORKING_DIR / src.name
            df2 = add_required_columns(df, src.name)
            written_to = write_any_file(df2, out_path)
            print(f"WORKING: {src.name} -> {written_to.name}")
        else:
            shutil.copy2(src, REJECTED_DIR / src.name)
            print(f"REJECT (col mismatch {df.shape[1]} != {template_cols}): {src.name}")


def process_edited_files(template_cols: int) -> None:
    """
    EDITED_FILES logic:
      - If not already in WORKING
      - If cols match -> write to WORKING + add columns
    """
    working_existing = list_filenames_lower(WORKING_DIR)

    candidates = sorted([
        p for p in EDITED_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".csv", ".xlsx")
    ])

    for src in candidates:
        if src.name.lower() in working_existing:
            print(f"SKIP EDITED (already in WORKING): {src.name}")
            continue

        try:
            df = read_any_file(src)
        except Exception as e:
            print(f"SKIP EDITED (read error): {src.name} -> {e}")
            continue

        if df.shape[1] == template_cols:
            out_path = WORKING_DIR / src.name
            df2 = add_required_columns(df, src.name)
            written_to = write_any_file(df2, out_path)
            print(f"WORKING (from EDITED): {src.name} -> {written_to.name}")
        else:
            print(f"SKIP EDITED (col mismatch {df.shape[1]} != {template_cols}): {src.name}")


if __name__ == "__main__":
    ensure_dirs(ORIGINAL_DIR, WORKING_DIR, REJECTED_DIR, EDITED_DIR)

    tmpl_cols = template_column_count(DATA_TEMPLATE)
    print(f"Template column count = {tmpl_cols}")

    process_original_files(tmpl_cols)
    process_edited_files(tmpl_cols)

    print("Done.")
