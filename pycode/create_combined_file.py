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

#spyder seems to get screwy with the wd sometimes
ROOT = Path(__file__).resolve().parents[1]   # goes up from pycode → repo root
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


from pycode.settings import *  # expects WORKING_FILES, DATA_TEMPLATE, COMBINED_FILE


# -------------------------
# Read helpers (Excel/CSV)
# -------------------------


def _normalize_strings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure ALL missing values are proper <NA>, not 'nan' strings.
    """
    df = df.copy()

    # ✅ Step 1: convert numpy NaN → pandas NA
    df = df.where(pd.notna(df), pd.NA)

    # ✅ Step 2: convert blank/whitespace → NA
    df = df.replace(r"^\s*$", pd.NA, regex=True)

    # ✅ Step 3: convert everything to pandas string dtype
    return df.astype("string")


def read_as_excel(path: Path) -> pd.DataFrame:
    # Read without forcing dtype; then normalize
    df = pd.read_excel(path, sheet_name=0, engine="openpyxl")
    return _normalize_strings(df)

def read_as_csv(path: Path) -> pd.DataFrame:
    # Read without forcing dtype; then normalize
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            df = pd.read_csv(path, encoding=enc)
            return _normalize_strings(df)
        except UnicodeDecodeError:
            continue
    df = pd.read_csv(path, encoding_errors="replace")
    return _normalize_strings(df)


def read_any_file_loose(path: Path) -> pd.DataFrame:
    """
    Attempt to read a file as Excel or CSV regardless of extension.
    Preference order:
      - .csv  -> CSV then Excel
      - .xlsx -> Excel then CSV
      - other -> Excel then CSV
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
# Agency code (NO fallback)
# -------------------------
def extract_agency_code(filename: str) -> Optional[str]:
    """
    NO fallback.
    Only accept digits as the final token before the extension
    preceded by a separator (space/underscore/hyphen).

    Examples:
      'District 17245.xlsx' -> '17245'
      'edited_District 17245.xlsx' -> '17245'
      'District 17245 v2.xlsx' -> None
    """
    m = re.search(r"(?:^|[ _-])(\d+)(?=\.(xlsx|csv)$)", filename, flags=re.IGNORECASE)
    return m.group(1) if m else None


# -------------------------
# Template columns
# -------------------------
def get_template_columns(template_path: Path) -> list:
    """
    Reads template headers (no data) and returns column names in order.
    """
    template_path = Path(template_path)
    if template_path.suffix.lower() == ".csv":
        tmpl = pd.read_csv(template_path, dtype=str, nrows=0)
    else:
        tmpl = pd.read_excel(template_path, dtype=str, nrows=0, engine="openpyxl")
    return tmpl.columns.tolist()


# -------------------------
# Combine logic
# -------------------------
def combine_working_files_using_template(
    working_dir: Path,
    template_path: Path,
    combined_file: Path,
    sheet_name: str = "combined"
) -> None:
    """
    Combine all files in WORKING_FILES into COMBINED_FILE.
    - Uses template columns as canonical headers/order.
    - Aligns each file by *position* (not by original headers).
    - Adds filenameFromDistrict + agency_code.
    - Skips unreadable files and files with wrong column counts.
    """
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

        # If a working file already contains filenameFromDistrict/agency_code, drop them
        # so we can re-add cleanly below (and avoid column count confusion).
        drop_candidates = [c for c in df.columns if str(c).strip().lower() in ("filenamefromdistrict", "agency_code")]
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

        # Add required columns
        df["filenameFromDistrict"] = f.name
        code = extract_agency_code(f.name)
        df["agency_code"] = pd.Series(code, index=df.index, dtype="string")  # <NA> if None

        dfs.append(df)
        print(f"[OK]  {f.name}  rows={len(df):,} cols={df.shape[1]}")

    # If nothing readable, still create the file with headers
    if not dfs:
        empty = pd.DataFrame(columns=template_cols + ["filenameFromDistrict", "agency_code"])
        with pd.ExcelWriter(combined_file, engine="openpyxl") as writer:
            empty.to_excel(writer, index=False, sheet_name=sheet_name)
        print(f"[DONE] No valid working files. Wrote empty combined workbook: {combined_file}")
        return

    combined_df = pd.concat(dfs, ignore_index=True, sort=False)

    # Order columns: template first, then the two added columns
    out_cols = template_cols + ["filenameFromDistrict", "agency_code"]
    combined_df = combined_df[out_cols]

    # Write output
    with pd.ExcelWriter(combined_file, engine="openpyxl") as writer:
        combined_df.to_excel(writer, index=False, sheet_name=sheet_name, na_rep="")

        # Optional: add a second sheet listing skipped files
        if skipped:
            skipped_df = pd.DataFrame(skipped, columns=["file", "reason", "detail"])
            skipped_df.to_excel(writer, index=False, sheet_name="skipped_files", na_rep="")

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