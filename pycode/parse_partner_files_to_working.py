# -*- coding: utf-8 -*-
"""
Created on Tue May 12 16:42:53 2026

@author: Chris.Wells

parse_district_data_files

parse_district_data_files + logging + edited_ handling in REJECTED_FILES

Enhancements:
- Log every file found in ORIGINAL_FILES regardless of extension
- Attempt to read as Excel or CSV; if unreadable, log only original_file + date_ingested
- Do not scan EDITED_FILES folder
- Promote edited_ files found in REJECTED_FILES into WORKING_FILES (keeping edited_ prefix)
- Update log STATUS to EDITED for the original filename (prefix removed)
"""
# -*- coding: utf-8 -*-
"""
parse_district_data_files + logging + edited_ handling in REJECTED_FILES

Enhancements:
- Log every file found in ORIGINAL_FILES regardless of extension
- Attempt to read as Excel or CSV; if unreadable, log only original_file + date_ingested
- Do not scan EDITED_FILES folder
- Promote edited_ files found in REJECTED_FILES into WORKING_FILES (keeping edited_ prefix)
- Update log STATUS to EDITED for the original filename (prefix removed)
"""

from pathlib import Path
import re
import shutil
import pandas as pd
from typing import Optional
from datetime import date

from pycode.settings import *

# TODO: switch above settings line to below. then use eg. settings.DATA_LOG
# to make the source of DATA_LOG and other settings explicit
# import pycode.settings as settings


# =========================
# CONFIG
# =========================
# _FILES = globals().get("_FILES", ORIGINAL_FILES.parent / "district_ingest_log.xlsx")

LOG_COLUMNS = [
    "original_file",        # name of file from ORIGINAL_FILES
    "date_ingested",        # today's date (on first log insert only)
    "non_blank_records",    # count rows not fully blank
    "STATUS",               # WORKING_FILES / REJECTED_FILES / EDITED (or missing)
    "notes",                # expected vs received columns
    "notes2",               # blank
]


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


def read_as_excel(path: Path) -> pd.DataFrame:
    """Try reading as Excel (first sheet)."""
    return pd.read_excel(path, dtype=str, sheet_name=0, engine="openpyxl")


def read_as_csv(path: Path) -> pd.DataFrame:
    """Try reading as CSV with a few encodings."""
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, dtype=str, encoding_errors="replace")


def read_any_file_loose(path: Path) -> pd.DataFrame:
    """
    Attempt to read ANY file as Excel or CSV.
    - If suffix is .xlsx -> try Excel first then CSV
    - If suffix is .csv  -> try CSV first then Excel
    - Otherwise          -> try Excel then CSV
    Raises the last exception if neither works.
    """
    suffix = path.suffix.lower()

    errors = []
    if suffix == ".csv":
        for fn in (read_as_csv, read_as_excel):
            try:
                return fn(path)
            except Exception as e:
                errors.append(e)
    elif suffix == ".xlsx":
        for fn in (read_as_excel, read_as_csv):
            try:
                return fn(path)
            except Exception as e:
                errors.append(e)
    else:
        for fn in (read_as_excel, read_as_csv):
            try:
                return fn(path)
            except Exception as e:
                errors.append(e)

    # Neither worked
    raise errors[-1] if errors else ValueError("Unknown read error")


def write_any_file(df: pd.DataFrame, out_path: Path) -> Path:
    """Write DataFrame back as CSV/XLSX based on output extension."""
    suffix = out_path.suffix.lower()

    if suffix == ".csv":
        df.to_csv(out_path, index=False)
        return out_path

    if suffix == ".xlsx":
        df.to_excel(out_path, index=False, engine="openpyxl", na_rep="")
        return out_path

    # If downstream wants the same filename but it's a weird extension, default to .xlsx
    out_path_xlsx = out_path.with_suffix(".xlsx")
    df.to_excel(out_path_xlsx, index=False, engine="openpyxl", na_rep="")
    return out_path_xlsx


def extract_agency_code(filename: str) -> Optional[str]:
    """
    NO fallback.
    Only accept digits as the final token before the extension
    preceded by a separator (space/underscore/hyphen).
    Works for .xlsx or .csv (case-insensitive).
    """
    m = re.search(r"(?:^|[ _-])(\d+)(?=\.(xlsx|csv)$)", filename, flags=re.IGNORECASE)
    return m.group(1) if m else None


def add_required_columns(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    """
    Add:
      - filenameFromDistrict
      - agency_code (string dtype; missing if not parsed)
    """
    df2 = df.copy()
    df2["filenameFromDistrict"] = filename

    code = extract_agency_code(filename)
    df2["agency_code"] = pd.Series(code, index=df2.index, dtype="string")

    return df2


def template_column_count(template_path: Path) -> int:
    """Read template and return number of columns."""
    tmpl_df = read_any_file_loose(template_path)
    return int(tmpl_df.shape[1])


def count_nonblank_records(df: pd.DataFrame) -> int:
    """
    Count rows that are not completely blank.
    Treat empty strings / whitespace as blank.
    """
    tmp = df.replace(r"^\s*$", pd.NA, regex=True)
    return int(tmp.dropna(how="all").shape[0])


def load_or_create_log(log_path: Path) -> pd.DataFrame:
    """Load log if exists; otherwise create empty log with required columns."""
    if log_path.exists():
        try:
            log_df = pd.read_excel(log_path, dtype="string", engine="openpyxl")
        except Exception:
            raise RuntimeError(f"Could not read log file: {log_path}. Is it open or corrupted?")
    else:
        log_df = pd.DataFrame(columns=LOG_COLUMNS)

    for c in LOG_COLUMNS:
        if c not in log_df.columns:
            log_df[c] = pd.NA
    return log_df[LOG_COLUMNS]


def save_log(log_df: pd.DataFrame, log_path: Path) -> None:
    """Save log safely (write temp then replace)."""
    tmp_path = log_path.with_suffix(".tmp.xlsx")
    log_df.to_excel(tmp_path, index=False, engine="openpyxl", na_rep="")
    tmp_path.replace(log_path)


def log_has_file(log_df: pd.DataFrame, original_filename: str) -> bool:
    """Case-insensitive check whether original_filename already exists in log."""
    if log_df.empty:
        return False
    s = log_df["original_file"].astype("string").fillna("")
    return (s.str.lower() == original_filename.lower()).any()


def append_log_row_if_missing(
    log_df: pd.DataFrame,
    original_filename: str,
    date_ingested: str,
    non_blank_records,
    status,
    notes,
    notes2=pd.NA
) -> pd.DataFrame:
    """
    Append a log row if original_filename is not already logged (case-insensitive).
    Does not overwrite existing rows.
    """
    if log_has_file(log_df, original_filename):
        return log_df

    new_row = {
        "original_file": original_filename,
        "date_ingested": date_ingested,
        "non_blank_records": non_blank_records,
        "STATUS": status,
        "notes": notes,
        "notes2": notes2,
    }
    return pd.concat([log_df, pd.DataFrame([new_row])], ignore_index=True)

def upsert_log_status_only(
    log_df: pd.DataFrame,
    filename: str,
    date_ingested: str,
    non_blank_records=pd.NA,
    status=pd.NA,
    notes=pd.NA,
    notes2=pd.NA
) -> pd.DataFrame:
    """
    If filename not in log -> append new row.
    If filename already in log -> update STATUS always,
      and fill other fields only if they are currently missing.
    Never overwrite date_ingested if already present.
    """
    mask = log_df["original_file"].astype("string").fillna("").str.lower() == filename.lower()

    if not mask.any():
        return append_log_row_if_missing(
            log_df,
            original_filename=filename,
            date_ingested=date_ingested,
            non_blank_records=non_blank_records,
            status=status,
            notes=notes,
            notes2=notes2
        )

    idx = log_df.index[mask][0]

    # Always update STATUS for this filename
    log_df.loc[idx, "STATUS"] = status

    # Fill only if missing
    if pd.isna(log_df.loc[idx, "non_blank_records"]) and not pd.isna(non_blank_records):
        log_df.loc[idx, "non_blank_records"] = non_blank_records

    if pd.isna(log_df.loc[idx, "notes"]) and not pd.isna(notes):
        log_df.loc[idx, "notes"] = notes

    if pd.isna(log_df.loc[idx, "notes2"]) and not pd.isna(notes2):
        log_df.loc[idx, "notes2"] = notes2

    # Do NOT overwrite date_ingested; only fill if missing
    if pd.isna(log_df.loc[idx, "date_ingested"]) and not pd.isna(date_ingested):
        log_df.loc[idx, "date_ingested"] = date_ingested

    return log_df


def update_log_status_to_edited(log_df: pd.DataFrame, original_filename: str) -> pd.DataFrame:
    """
    Update STATUS to 'EDITED' for the row matching original_filename (case-insensitive).
    If no row exists, create one with today's date and missing other fields.
    """
    today_str = date.today().isoformat()
    mask = log_df["original_file"].astype("string").fillna("").str.lower() == original_filename.lower()

    if mask.any():
        log_df.loc[mask, "STATUS"] = "EDITED"
        return log_df

    # If original wasn't logged, add minimal row (only original_file + date_ingested + STATUS)
    return append_log_row_if_missing(
        log_df,
        original_filename=original_filename,
        date_ingested=today_str,
        non_blank_records=pd.NA,
        status="EDITED",
        notes=pd.NA,
        notes2=pd.NA
    )


def is_edited_file(filename: str) -> bool:
    """True if filename begins with edited_ (case-insensitive)."""
    return re.match(r"^edited_", filename, flags=re.IGNORECASE) is not None


def strip_edited_prefix(filename: str) -> str:
    """Remove leading edited_ (case-insensitive) once."""
    return re.sub(r"^edited_", "", filename, flags=re.IGNORECASE)


# =========================
# Main processing logic
# =========================

def process_original_files(template_cols: int, log_df: pd.DataFrame) -> pd.DataFrame:
    """
    Requirements:
    - Log EVERY file in ORIGINAL regardless of extension.
    - If file cannot be read as Excel or CSV:
        - log original_file + date_ingested only
        - leave other fields blank (missing)
    - If readable:
        - decide WORKING vs REJECTED based on column count match
        - copy/write accordingly (only for readable files)
        - log without overwriting existing rows
    - If file already exists in WORKING or REJECTED:
        - do not copy again
        - but STILL log it if missing; if readable, fill counts/notes and STATUS based on where it already exists
    """
    working_existing = list_filenames_lower(WORKING_FILES)
    rejected_existing = list_filenames_lower(REJECTED_FILES)

    candidates = sorted([p for p in ORIGINAL_FILES.iterdir() if p.is_file()])
    today_str = date.today().isoformat()

    for src in candidates:
        # Always attempt to log if not already logged
        if log_has_file(log_df, src.name):
            # Don't overwrite anything for already-logged files
            # (edited promotions are handled elsewhere)
            continue

        # Try reading as Excel or CSV, regardless of extension
        try:
            df = read_any_file_loose(src)
            readable = True
        except Exception as e:
            readable = False
            df = None

        if not readable:
            # Leave everything except original_file/date_ingested missing
            log_df = append_log_row_if_missing(
                log_df,
                original_filename=src.name,
                date_ingested=today_str,
                non_blank_records=pd.NA,
                status=pd.NA,
                notes=pd.NA,
                notes2=pd.NA
            )
            print(f"LOG ONLY (unreadable as excel/csv): {src.name}")
            continue

        # Readable: compute log metrics
        
            received_cols = int(df.shape[1])
            non_blank = count_nonblank_records(df)
            
            # Only populate notes if mismatch
            if received_cols != template_cols:
                notes = f"expected_cols={template_cols}; received_cols={received_cols}"
            else:
                notes = pd.NA


        # If file already exists elsewhere, do not recopy; set STATUS to where it exists
        src_lc = src.name.lower()
        if src_lc in working_existing:
            status = "WORKING_FILES"
            log_df = append_log_row_if_missing(log_df, src.name, today_str, non_blank, status, notes, pd.NA)
            print(f"LOG (already in WORKING): {src.name}")
            continue

        if src_lc in rejected_existing:
            status = "REJECTED_FILES"
            log_df = append_log_row_if_missing(log_df, src.name, today_str, non_blank, status, notes, pd.NA)
            print(f"LOG (already in REJECTED): {src.name}")
            continue

        # Not present elsewhere: apply column-count rule and copy/write
        if received_cols == template_cols:
            out_path = WORKING_FILES / src.name
            df2 = add_required_columns(df, src.name)
            written_to = write_any_file(df2, out_path)
            status = "WORKING_FILES"
            print(f"WORKING: {src.name} -> {written_to.name}")
        else:
            shutil.copy2(src, REJECTED_FILES / src.name)
            status = "REJECTED_FILES"
            print(f"REJECT (col mismatch {received_cols} != {template_cols}): {src.name}")

        log_df = append_log_row_if_missing(
            log_df,
            original_filename=src.name,
            date_ingested=today_str,
            non_blank_records=non_blank,
            status=status,
            notes=notes,
            notes2=pd.NA
        )

    return log_df

def process_original_files(template_cols: int, log_df: pd.DataFrame) -> pd.DataFrame:
    """
    Requirements:
    - Log EVERY file in ORIGINAL_FILES regardless of extension.
    - If unreadable as excel/csv: log original_file + date_ingested only; rest missing.
    - If readable: compute non_blank_records; route to WORKING/REJECTED based on col count.
    - If file already exists in WORKING/REJECTED: do not recopy; just log status.
    - Do not overwrite log entries if already present.
    - Only write notes when column count mismatches.
    """
    working_existing = list_filenames_lower(WORKING_FILES)
    rejected_existing = list_filenames_lower(REJECTED_FILES)

    candidates = sorted([p for p in ORIGINAL_FILES.iterdir() if p.is_file()])
    today_str = date.today().isoformat()

    for src in candidates:
        # --- ALWAYS initialize so they exist on every path ---
        non_blank = pd.NA
        status = pd.NA
        notes = pd.NA

        # don't overwrite existing log rows
        if log_has_file(log_df, src.name):
            continue

        # attempt read regardless of extension
        try:
            df = read_any_file_loose(src)
        except Exception:
            # unreadable: log only file + date
            log_df = append_log_row_if_missing(
                log_df,
                original_filename=src.name,
                date_ingested=today_str,
                non_blank_records=pd.NA,
                status=pd.NA,
                notes=pd.NA,
                notes2=pd.NA
            )
            print(f"LOG ONLY (unreadable as excel/csv): {src.name}")
            continue

        # readable: compute counts
        received_cols = int(df.shape[1])
        non_blank = count_nonblank_records(df)

        # notes only if mismatch
        if received_cols != template_cols:
            notes = f"expected_cols={template_cols}; received_cols={received_cols}"
        else:
            notes = pd.NA

        src_lc = src.name.lower()

        # already exists? log location, do not copy
        if src_lc in working_existing:
            status = "WORKING_FILES"
            log_df = append_log_row_if_missing(
                log_df,
                original_filename=src.name,
                date_ingested=today_str,
                non_blank_records=non_blank,
                status=status,
                notes=notes,
                notes2=pd.NA
            )
            print(f"LOG (already in WORKING): {src.name}")
            continue

        if src_lc in rejected_existing:
            status = "REJECTED_FILES"
            log_df = append_log_row_if_missing(
                log_df,
                original_filename=src.name,
                date_ingested=today_str,
                non_blank_records=non_blank,
                status=status,
                notes=notes,
                notes2=pd.NA
            )
            print(f"LOG (already in REJECTED): {src.name}")
            continue

        # not present: route
        if received_cols == template_cols:
            out_path = WORKING_FILES / src.name
            df2 = add_required_columns(df, src.name)
            written_to = write_any_file(df2, out_path)
            status = "WORKING_FILES"
            print(f"WORKING: {src.name} -> {written_to.name}")
        else:
            shutil.copy2(src, REJECTED_FILES / src.name)
            status = "REJECTED_FILES"
            print(f"REJECT (col mismatch {received_cols} != {template_cols}): {src.name}")

        # log final outcome (variables are guaranteed defined)
        log_df = append_log_row_if_missing(
            log_df,
            original_filename=src.name,
            date_ingested=today_str,
            non_blank_records=non_blank,
            status=status,
            notes=notes,
            notes2=pd.NA
        )

    return log_df


def process_edited_files_in_rejected(template_cols: int, log_df: pd.DataFrame) -> pd.DataFrame:
    """
    REQUIRED behavior:
    - Leave rejected files in REJECTED_FILES and in the log.
    - If a file in REJECTED_FILES starts with edited_:
        - Log it as its own entry (edited filename).
        - If readable and cols match template:
            - COPY it into WORKING_FILES as a new file (keep edited_ prefix)
            - Keep the edited file in REJECTED_FILES too
            - STATUS = EDITED_WORKING
        - If readable and cols mismatch:
            - Leave it in REJECTED_FILES
            - STATUS = EDITED_REJECTED
            - notes = expected/received
        - If unreadable:
            - Log filename + date only; leave rest missing
    - If the edited_ filename already exists in the log, update its STATUS (don’t overwrite date_ingested).
    """
    today_str = date.today().isoformat()

    candidates = sorted([
        p for p in REJECTED_FILES.iterdir()
        if p.is_file() and is_edited_file(p.name)
    ])

    for src in candidates:
        # Defaults
        non_blank = pd.NA
        status = pd.NA
        notes = pd.NA

        # Try to read as Excel/CSV regardless of extension
        try:
            df = read_any_file_loose(src)
        except Exception as e:
            print(f"LOG ONLY (edited_ unreadable as excel/csv): {src.name} -> {e}")
            log_df = upsert_log_status_only(
                log_df,
                filename=src.name,
                date_ingested=today_str,
                non_blank_records=pd.NA,
                status=pd.NA,
                notes=pd.NA,
                notes2=pd.NA
            )
            continue

        received_cols = int(df.shape[1])
        non_blank = count_nonblank_records(df)

        if received_cols == template_cols:
            # COPY into WORKING (keep edited_ prefix). Do NOT remove from REJECTED.
            out_path = WORKING_FILES / src.name

            # Write as a pandas-produced file with your standard added columns
            df2 = add_required_columns(df, src.name)
            written_to = write_any_file(df2, out_path)
            print(f"EDITED -> WORKING (copied, rejected retained): {src.name} -> {written_to.name}")

            status = "EDITED_WORKING"
            notes = pd.NA  # only record cols in notes when mismatch

        else:
            status = "EDITED_REJECTED"
            notes = f"expected_cols={template_cols}; received_cols={received_cols}"
            print(f"EDITED remains REJECTED (col mismatch {received_cols} != {template_cols}): {src.name}")

        # Log as its own entry (edited filename). Update STATUS if already logged.
        log_df = upsert_log_status_only(
            log_df,
            filename=src.name,
            date_ingested=today_str,
            non_blank_records=non_blank,
            status=status,
            notes=notes,
            notes2=pd.NA
        )

    return log_df




if __name__ == "__main__":
    ensure_dirs(ORIGINAL_FILES, WORKING_FILES, REJECTED_FILES)

    log_df = load_or_create_log(DATA_LOG)

    tmpl_cols = template_column_count(DATA_TEMPLATE)
    print(f"Template column count = {tmpl_cols}")

    # Log + process originals (logs ALL files in ORIGINAL_FILES, even weird extensions)
    log_df = process_original_files(tmpl_cols, log_df)

    # Promote edited_ files living in REJECTED_FILES
    log_df = process_edited_files_in_rejected(tmpl_cols, log_df)

    save_log(log_df, DATA_LOG)
    print(f"Log saved to: {DATA_LOG}")

    print("Done.")