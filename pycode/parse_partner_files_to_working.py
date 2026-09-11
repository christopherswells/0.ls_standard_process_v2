# -*- coding: utf-8 -*-
"""Incrementally route partner files from ORIGINAL_FILES to WORKING_FILES."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import shutil
from typing import Optional

import pandas as pd

try:
    from pycode.settings import *
except ModuleNotFoundError:
    # Allows the script to run when launched directly from the pycode folder.
    from settings import *

REJECTED_PREFIX = "REJECTED_"
EDITED_PREFIX = "EDITED_"
METADATA_COLUMNS = ("filenameFromDistrict", "agency_code")
LOG_COLUMNS = ["original_file", "date_received", "working_date",
               "non_blank_records", "STATUS", "notes", "notes2"]
LEGACY_DATE_COLUMN = "date_ingested"


def ensure_dirs(*folders: Path) -> None:
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


def read_excel(path: Path) -> pd.DataFrame:
    return pd.read_excel(path, dtype=str, sheet_name=0, engine="openpyxl")


def read_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return pd.read_csv(path, dtype=str, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, dtype=str, encoding_errors="replace")


def read_file(path: Path) -> pd.DataFrame:
    readers = (read_csv, read_excel) if path.suffix.lower() == ".csv" else (read_excel, read_csv)
    errors = []
    for reader in readers:
        try:
            return reader(path)
        except Exception as exc:
            errors.append(exc)
    raise errors[-1]


def write_file(df: pd.DataFrame, path: Path) -> Path:
    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False)
        return path
    output = path if path.suffix.lower() == ".xlsx" else path.with_suffix(".xlsx")
    df.to_excel(output, index=False, engine="openpyxl", na_rep="")
    return output


def extract_agency_code(filename: str) -> Optional[str]:
    match = re.search(r"(?:^|[ _-])(\d+)(?=\.(?:xlsx|csv)$)", filename, re.IGNORECASE)
    return match.group(1) if match else None


def original_filename(filename: str) -> str:
    value = str(filename)
    while re.match(r"^_*(?:REJECTED_|EDITED_)", value, re.IGNORECASE):
        value = re.sub(r"^_*(?:REJECTED_|EDITED_)", "", value,
                       count=1, flags=re.IGNORECASE)
    return value


def has_status(filename: str, prefix: str) -> bool:
    return bool(re.match(rf"^_*{re.escape(prefix)}", str(filename), re.IGNORECASE))


def is_edited_lifecycle(filename: str) -> bool:
    return bool(re.match(r"^_*(?:REJECTED_)?EDITED_", str(filename), re.IGNORECASE))


def rejected_filename(filename: str) -> str:
    base = original_filename(filename)
    return (REJECTED_PREFIX + EDITED_PREFIX + base
            if is_edited_lifecycle(filename)
            else REJECTED_PREFIX + base)


def edited_filename(filename: str) -> str:
    return EDITED_PREFIX + original_filename(filename)


def source_columns(df: pd.DataFrame) -> list:
    metadata = {column.lower() for column in METADATA_COLUMNS}
    return [column for column in df.columns if str(column).lower() not in metadata]


def source_only(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[:, source_columns(df)].copy()


def partner_column_count(df: pd.DataFrame) -> int:
    return len(source_columns(df))


def nonblank_record_count(df: pd.DataFrame) -> int:
    cleaned = source_only(df).replace(r"^\s*$", pd.NA, regex=True)
    return int(cleaned.dropna(how="all").shape[0])


def add_metadata(df: pd.DataFrame, original_name: str) -> pd.DataFrame:
    output = source_only(df)
    output["filenameFromDistrict"] = original_name
    output["agency_code"] = pd.Series(
        extract_agency_code(original_name), index=output.index, dtype="string")
    return output


def same_path(left: Path, right: Path) -> bool:
    return str(left.resolve()).lower() == str(right.resolve()).lower()


def remove_conflict(target: Path, current: Optional[Path] = None) -> None:
    for item in target.parent.iterdir():
        if not item.is_file():
            continue
        if current is not None and same_path(item, current):
            continue
        if item.name.lower() == target.name.lower():
            item.unlink()


def rename_working(source: Path, new_name: str) -> Path:
    target = source.with_name(new_name)
    if source.name == target.name:
        return source
    remove_conflict(target, current=source)
    if same_path(source, target):
        counter = 0
        while True:
            suffix = "" if counter == 0 else f"_{counter}"
            temporary = source.with_name(f"__tmp_case_change__{suffix}_{source.name}")
            if not temporary.exists():
                break
            counter += 1
        source.replace(temporary)
        try:
            temporary.replace(target)
        except Exception:
            if temporary.exists() and not source.exists():
                temporary.replace(source)
            raise
    else:
        source.replace(target)
    return target


def is_missing(value) -> bool:
    return pd.isna(value) or (isinstance(value, str) and not value.strip())


def load_log(path: Path) -> pd.DataFrame:
    log = (pd.read_excel(path, dtype="string", engine="openpyxl")
           if path.exists() else pd.DataFrame(columns=LOG_COLUMNS))
    if "date_received" not in log.columns:
        log["date_received"] = log[LEGACY_DATE_COLUMN] if LEGACY_DATE_COLUMN in log.columns else pd.NA
    elif LEGACY_DATE_COLUMN in log.columns:
        blank = log["date_received"].isna() | log["date_received"].fillna("").str.strip().eq("")
        log.loc[blank, "date_received"] = log.loc[blank, LEGACY_DATE_COLUMN]
    for column in LOG_COLUMNS:
        if column not in log.columns:
            log[column] = pd.NA
    log["original_file"] = log["original_file"].map(
        lambda value: original_filename(value) if not is_missing(value) else value)
    extras = [column for column in log.columns if column not in LOG_COLUMNS]
    return log[LOG_COLUMNS + extras]


def save_log(log: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(".tmp.xlsx")
    log.to_excel(temporary, index=False, engine="openpyxl", na_rep="")
    temporary.replace(path)


def log_mask(log: pd.DataFrame, filename: str) -> pd.Series:
    if log.empty:
        return pd.Series(False, index=log.index, dtype=bool)
    target = original_filename(filename).lower()
    names = log["original_file"].astype("string").fillna("")
    return names.map(lambda value: original_filename(value).lower() == target)


def already_logged(log: pd.DataFrame, filename: str) -> bool:
    return bool(log_mask(log, filename).any())


def upsert_log(log, filename, received_date, working_date, records, status, note):
    """Preserve first dates/manual notes; store record counts as log-safe text."""
    original = original_filename(filename)
    record_text = str(records) if not is_missing(records) else pd.NA
    mask = log_mask(log, original)
    if not mask.any():
        row = {column: pd.NA for column in log.columns}
        row.update({"original_file": original, "date_received": received_date,
                    "working_date": working_date, "non_blank_records": record_text,
                    "STATUS": status, "notes": note, "notes2": pd.NA})
        return pd.concat([log, pd.DataFrame([row])], ignore_index=True)
    idx = log.index[mask][0]
    log.at[idx, "original_file"] = original
    if is_missing(log.at[idx, "date_received"]):
        log.at[idx, "date_received"] = received_date
    if not is_missing(working_date) and is_missing(log.at[idx, "working_date"]):
        log.at[idx, "working_date"] = working_date
    if not is_missing(record_text):
        log.at[idx, "non_blank_records"] = record_text
    log.at[idx, "STATUS"] = status
    if not is_missing(note) and is_missing(log.at[idx, "notes"]):
        log.at[idx, "notes"] = note
    return log


def process_new_originals(expected: int, log: pd.DataFrame) -> pd.DataFrame:
    today = date.today().isoformat()
    candidates = sorted(p for p in ORIGINAL_FILES.iterdir()
                        if p.is_file() and not p.name.startswith("."))
    for source in candidates:
        original = source.name
        if already_logged(log, original):
            print(f"SKIPPED ALREADY PROCESSED: {source.name}")
            continue
        try:
            df = read_file(source)
        except Exception as exc:
            target = WORKING_FILES / rejected_filename(original)
            remove_conflict(target)
            shutil.copy2(source, target)
            log = upsert_log(log, original, today, pd.NA, pd.NA,
                             "REJECTED_UNREADABLE",
                             f"unable_to_read_as_excel_or_csv={type(exc).__name__}")
            print(f"REJECTED UNREADABLE: {source.name} -> {target.name}")
            continue
        received = partner_column_count(df)
        records = nonblank_record_count(df)
        passed = received == expected
        target = WORKING_FILES / (original if passed else rejected_filename(original))
        remove_conflict(target)
        written = write_file(add_metadata(df, original), target)
        log = upsert_log(log, original, today, today if passed else pd.NA, records,
                         "WORKING" if passed else "REJECTED_WORKING_FOLDER",
                         pd.NA if passed else f"expected_cols={expected}; received_cols={received}")
        print(f"{'WORKING' if passed else 'REJECTED'}: {source.name} -> {written.name}")
    return log


def process_flagged_working(expected: int, log: pd.DataFrame) -> pd.DataFrame:
    today = date.today().isoformat()
    candidates = sorted(p for p in WORKING_FILES.iterdir()
                        if p.is_file() and not p.name.startswith(".") and
                        (has_status(p.name, REJECTED_PREFIX) or
                         has_status(p.name, EDITED_PREFIX)))
    for source in candidates:
        if not source.exists():
            continue
        original = original_filename(source.name)
        was_rejected = has_status(source.name, REJECTED_PREFIX)
        was_edited = has_status(source.name, EDITED_PREFIX)
        normalized = rejected_filename(source.name) if was_rejected else edited_filename(source.name)
        source = rename_working(source, normalized)
        try:
            df = read_file(source)
        except Exception as exc:
            renamed = rename_working(source, rejected_filename(source.name))
            log = upsert_log(log, original, today, pd.NA, pd.NA,
                             "REJECTED_UNREADABLE",
                             f"unable_to_read_as_excel_or_csv={type(exc).__name__}")
            print(f"STILL UNREADABLE: {source.name} -> {renamed.name}")
            continue
        received = partner_column_count(df)
        records = nonblank_record_count(df)
        if received == expected:
            renamed = rename_working(source, edited_filename(source.name)) if was_rejected else source
            written = write_file(add_metadata(df, original), renamed)
            log = upsert_log(log, original, today, today, records, "EDITED_WORKING", pd.NA)
            print(f"EDITED CONFIRMED: {source.name} -> {written.name}")
        else:
            desired = rejected_filename(source.name) if was_edited else rejected_filename(original)
            renamed = rename_working(source, desired)
            log = upsert_log(log, original, today, pd.NA, records,
                             "REJECTED_WORKING_FOLDER",
                             f"expected_cols={expected}; received_cols={received}")
            print(f"FAILED FIELD CHECK: {source.name} -> {renamed.name}")
    return log


if __name__ == "__main__":
    ensure_dirs(ORIGINAL_FILES, WORKING_FILES)
    log_df = load_log(DATA_LOG)
    expected_columns = partner_column_count(read_file(DATA_TEMPLATE))
    print(f"Template partner-data column count = {expected_columns}")
    log_df = process_new_originals(expected_columns, log_df)
    log_df = process_flagged_working(expected_columns, log_df)
    save_log(log_df, DATA_LOG)
    print(f"Log saved to: {DATA_LOG}")
    print("Done.")
