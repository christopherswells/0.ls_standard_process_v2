# -*- coding: utf-8 -*-
"""
Created on Wed May 13 10:41:35 2026

@author: Chris.Wells
"""
from pathlib import Path
import re
import pandas as pd
from typing import Optional
import sys

# Spyder sometimes gets screwy with the working directory
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pycode.settings import *  # expects WORKING_FILES, DATA_TEMPLATE, COMBINED_FILE


# -------------------------
# Read helpers (Excel/CSV)
# -------------------------

def _normalize_strings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure ALL values are treated as TEXT.
    Convert NaN → <NA>, blank → <NA>, enforce string dtype,
    and uppercase column headers.
    """
    df = df.copy()

    # Convert numpy NaN → pandas NA
    df = df.where(pd.notna(df), pd.NA)

    # Convert blank/whitespace → NA
    df = df.replace(r"^\s*$", pd.NA, regex=True)

    # Force all columns to string dtype (prevents .0, date parsing, etc.)
    df = df.astype("string")

    # Uppercase column headers
    df.columns = [str(c).upper() for c in df.columns]

    return df


def read_as_excel(path: Path) -> pd.DataFrame:
    # Read everything as text
    df = pd.read_excel(path, sheet_name=0, dtype=str, engine="openpyxl")
    return _normalize_strings(df)


def read_as_csv(path: Path) -> pd.DataFrame:
    # Read everything as text
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc)
            return _normalize_strings(df)
        except UnicodeDecodeError:
            continue
    df = pd.read_csv(path, dtype=str, encoding_errors="replace")
    return _normalize_strings(df)


def read_any_file_loose(path: Path) -> pd.DataFrame:
    """
    Attempt to read a file as Excel or CSV regardless of extension.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        readers = (read_as_csv, read_as_excel)
    elif suffix == ".xlsx":
        readers = (read_as_excel, read_as_csv)
    else:
        readers = (read_as_excel, read_as_csv)

    last_err = None
    for fn in readers:
        try:
            return fn(path)
        except Exception as e:
            last_err = e
    raise last_err


# -------------------------
# Agency code extraction
# -------------------------

def extract_agency_code(filename: str) -> Optional[str]:
    """
    Extract digits before extension, preceded by space/underscore/hyphen.
    """
    m = re.search(r"(?:^|[ _-])(\d+)(?=\.(xlsx|csv)$)", filename, flags=re.IGNORECASE)
    return m.group(1) if m else None


# -------------------------
# Template columns
# -------------------------

def get_template_columns(template_path: Path) -> list:
    """
    Reads template headers (no data) and returns column names in order,
    uppercased.
    """
    template_path = Path(template_path)
    if template_path.suffix.lower() == ".csv":
        tmpl = pd.read_csv(template_path, dtype=str, nrows=0)
    else:
        tmpl = pd.read_excel(template_path, dtype=str, nrows=0, engine="openpyxl")

    return [str(c).upper() for c in tmpl.columns.tolist()]


# -------------------------
# Combine logic
# -------------------------

def combine_working_files_using_template(
    working_dir: Path,
    template_path: Path,
    combined_file: Path,
    sheet_name: str = "combined"
) -> None:

    working_dir = Path(working_dir)
    combined_file = Path(combined_file)
    combined_file.parent.mkdir(parents=True, exist_ok=True)

    template_cols = get_template_columns(template_path)
    n_template = len(template_cols)

    files = sorted([p for p in working_dir.iterdir() if p.is_file()])

    dfs = []
    skipped = []

    print(f"Template columns: {n_template}")

    for f in files:
        try:
            df = read_any_file_loose(f)
        except Exception as e:
            skipped.append((f.name, "UNREADABLE", str(e)))
            print(f"[SKIP] Unreadable as excel/csv: {f.name} ({e})")
            continue

        # Drop pre-existing metadata columns (uppercase now)
        drop_candidates = [
            c for c in df.columns
            if c in ("FILENAMEFROMDISTRICT", "AGENCY_CODE", "AGENCYCODE")
        ]
        if drop_candidates:
            df = df.drop(columns=drop_candidates, errors="ignore")

        # Validate column count matches template
        if df.shape[1] != n_template:
            skipped.append((f.name, "COL_MISMATCH", f"expected {n_template}, got {df.shape[1]}"))
            print(f"[SKIP] Column mismatch: {f.name} (expected {n_template}, got {df.shape[1]})")
            continue

        # Force template headers by position
        df = df.copy()
        df.columns = template_cols

        # Add required metadata columns (uppercase)
        df["FILENAMEFROMDISTRICT"] = f.name
        code = extract_agency_code(f.name)
        df["AGENCYCODE"] = pd.Series(code, index=df.index, dtype="string")

        dfs.append(df)
        print(f"[OK]  {f.name}  rows={len(df):,} cols={df.shape[1]}")

    # If nothing readable, still create the file with headers
    if not dfs:
        empty_cols = template_cols + ["FILENAMEFROMDISTRICT", "AGENCYCODE"]
        empty = pd.DataFrame(columns=empty_cols)
        with pd.ExcelWriter(combined_file, engine="openpyxl") as writer:
            empty.to_excel(writer, index=False, sheet_name=sheet_name)
        print(f"[DONE] No valid working files. Wrote empty combined workbook: {combined_file}")
        return

    combined_df = pd.concat(dfs, ignore_index=True, sort=False)

    # Order columns: template first, then metadata columns
    out_cols = template_cols + ["FILENAMEFROMDISTRICT", "AGENCYCODE"]
    combined_df = combined_df[out_cols]

    # Write excel output (all fields remain TEXT)
    with pd.ExcelWriter(combined_file, engine="openpyxl") as writer:
        combined_df.to_excel(writer, index=False, sheet_name=sheet_name, na_rep="")

        if skipped:
            skipped_df = pd.DataFrame(skipped, columns=["FILE", "REASON", "DETAIL"])
            skipped_df.to_excel(writer, index=False, sheet_name="SKIPPED_FILES", na_rep="")

    print(f"[DONE] Wrote combined file: {combined_file}")
    print(f"       Files combined: {len(dfs)} | Files skipped: {len(skipped)}")
    print(f"       Combined rows: {len(combined_df):,} | Combined cols: {combined_df.shape[1]}")


if __name__ == "__main__":
    combine_working_files_using_template(
        working_dir=WORKING_FILES,
        template_path=DATA_TEMPLATE,
        combined_file=COMBINED_FILE,
        sheet_name="combined"
    )
