# -*- coding: utf-8 -*-
"""
Created on Wed May 13 16:40:22 2026

@author: Chris.Wells
"""
import re
import pandas as pd
from typing import List, Tuple
import sys
from pathlib import Path
from typing import Optional

# Spyder sometimes gets screwy with the working directory
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pycode.settings import *

# Suffixes already uppercase
# SUFFIXES = ["SS", "PLCODE", "PLDESC", "TESTNAME", "TESTDATE", "RETEST"]


def pivot_scores_long_no_impute(
    combineddf: pd.DataFrame,
    drop_rows_missing_ss: bool = False,
    drop_rows_all_scores_missing: bool = True,
) -> pd.DataFrame:
    """
    Wide -> long without imputation.
    Score fields end with _{SS, PLCODE, PLDESC, TESTNAME, TESTDATE, RETEST}.
    SUBJECT = part before the last underscore.
    """

    df = combineddf.copy()

    # Identify subject score columns strictly by suffix (case-insensitive)
    suffix_pattern = re.compile(
        rf"^(?P<subject>.+)_(?P<suffix>{'|'.join(SUFFIXES)})$",
        re.IGNORECASE
    )

    score_cols: List[str] = []
    subjects: List[str] = []
    col_to_suffix: dict = {}

    for c in df.columns:
        m = suffix_pattern.match(str(c))
        if m:
            score_cols.append(c)
            subj = m.group("subject")
            suf = m.group("suffix").upper()
            col_to_suffix[c] = (subj, suf)
            subjects.append(subj)

    subjects = sorted(pd.unique(subjects))

    # All non-score columns (uppercase now)
    non_subject_fields = [c for c in df.columns if c not in score_cols]

    long_parts = []

    for subj in subjects:
        subject_cols = [c for c in score_cols if col_to_suffix[c][0] == subj]

        temp = df[non_subject_fields + subject_cols].copy()
        temp["SUBJECT"] = subj

        # Rename subject columns to suffix only
        rename_map = {c: col_to_suffix[c][1] for c in subject_cols}
        temp = temp.rename(columns=rename_map)

        # Ensure all expected suffix columns exist
        for suf in SUFFIXES:
            if suf not in temp.columns:
                temp[suf] = pd.NA

        temp = temp[non_subject_fields + ["SUBJECT"] + SUFFIXES]
        long_parts.append(temp)

    if not long_parts:
        out = df[non_subject_fields].copy()
        out["SUBJECT"] = pd.NA
        for suf in SUFFIXES:
            out[suf] = pd.NA
        return out

    long_df = pd.concat(long_parts, ignore_index=True)

    # Clean blank strings → NA
    long_df[SUFFIXES] = long_df[SUFFIXES].replace(r"^\s*$", pd.NA, regex=True)

    # Drop rules
    if drop_rows_all_scores_missing:
        long_df = long_df.dropna(subset=SUFFIXES, how="all")

    if drop_rows_missing_ss:
        long_df = long_df.dropna(subset=["SS"])

    return long_df


def _normalize_strings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize missing values and uppercase column headers.
    """
    df = df.copy()

    df = df.where(pd.notna(df), pd.NA)
    df = df.replace(r"^\s*$", pd.NA, regex=True)
    df = df.astype("string")

    # Uppercase column headers
    df.columns = [str(c).upper() for c in df.columns]

    return df


def rename_columns_upper_with_prefix(df: pd.DataFrame, prefix: str = "D_") -> pd.DataFrame:
    """
    Convert all column names to uppercase and prepend prefix.
    """
    df = df.copy()
    df.columns = [f"{prefix}{str(col).strip().upper()}" for col in df.columns]
    return df


# ---------------------------------------------------------
# Load wide combined file (now uppercase headers)
# ---------------------------------------------------------

if "combinedDf" in globals() and isinstance(combinedDf, pd.DataFrame):
    df_wide = combinedDf
else:
    df_wide = pd.read_excel(COMBINED_FILE, dtype=str, engine="openpyxl")
    df_wide = _normalize_strings(df_wide)

# ---------------------------------------------------------
# Pivot wide → long
# ---------------------------------------------------------

df_long = pivot_scores_long_no_impute(
    df_wide,
    drop_rows_missing_ss=True,
    drop_rows_all_scores_missing=True
)

# ---------------------------------------------------------
# Rename long columns with prefix (already uppercase)
# ---------------------------------------------------------

df_long = rename_columns_upper_with_prefix(df_long)



#==============================================================
# CLEAN LONG FILE FOR UPLOAD
#==============================================================



#----------------------------------------------------
# CAST TO INT AS _CLEAN
#---------------------------------------------------
def add_clean_int_columns(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    """
    For each column in `cols`, create a new column named COL_CLEAN
    and cast it to integer safely:
      - blank/whitespace -> NA
      - non-numeric -> NA
      - original column remains untouched
    """
    df = df.copy()

    for col in cols:
        clean_col = f"{col}_CLEAN"

        # Normalize blanks → NA
        series = df[col].replace(r"^\s*$", pd.NA, regex=True)

        # Convert to integer safely
        df[clean_col] = pd.to_numeric(series, errors="coerce").astype("Int64")

    return df

df_long = add_clean_int_columns(
    df_long,
    cols=[
        "D_LOCAL_STID",
        "D_STATE_STID",
        "D_AGENCYCODE",
        "D_SS",
        "D_PLCODE",
    ]
)



#----------------------------------------------------
# CLEAN DATES
# mm/dd/yyyy
# yyyy-mm-dd
# yyyy/mm/dd
# mmddyyyy
# mddyyyy
# mmddyy
# yyyymmdd
# timestamps like 2024-05-01 12:30:00
#----------------------------------------------------
import pandas as pd
import re
from datetime import datetime

def _parse_term_to_year(term: str) -> Optional[int]:
    """
    Convert D_TERM like 'SPRING 2025' or 'FALL 2024' into a year.
    Returns None if not parseable.
    """
    if term is None or pd.isna(term):
        return None

    m = re.search(r"(\d{4})", str(term))
    return int(m.group(1)) if m else None


def _safe_parse_date(raw: str) -> Optional[datetime]:
    """
    Try multiple formats to parse a date.
    Handles:
      - standard delimited dates
      - timestamps with time (strips time)
      - 8-digit: mmddyyyy or yyyymmdd (validated)
      - 7-digit: mddyyyy (e.g., 3112025 -> 03/11/2025)
      - 6-digit: mmddyy (2-digit year)
    Returns datetime or None.
    """
    if raw is None or pd.isna(raw):
        return None

    s = str(raw).strip()

    # Strip time portion if present
    s = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?$", "", s)

    # Digits-only handling
    if re.fullmatch(r"\d+", s):
        digits = s

        # 8 digits → try mmddyyyy then yyyymmdd with validation
        if len(digits) == 8:
            mm = int(digits[0:2])
            dd = int(digits[2:4])
            yyyy = int(digits[4:8])

            # mmddyyyy
            try:
                if 1 <= mm <= 12 and 1 <= dd <= 31:
                    return datetime(yyyy, mm, dd)
            except:
                pass

            # yyyymmdd
            yyyy2 = int(digits[0:4])
            mm2 = int(digits[4:6])
            dd2 = int(digits[6:8])
            try:
                if 1 <= mm2 <= 12 and 1 <= dd2 <= 31:
                    return datetime(yyyy2, mm2, dd2)
            except:
                pass

        # 7 digits → mddyyyy (e.g., 3112025 -> 03/11/2025)
        if len(digits) == 7:
            mm = int(digits[0])      # first digit
            dd = int(digits[1:3])    # next two
            yyyy = int(digits[3:7])  # last four
            try:
                if 1 <= mm <= 12 and 1 <= dd <= 31:
                    return datetime(yyyy, mm, dd)
            except:
                pass

        # 6 digits → mmddyy
        if len(digits) == 6:
            mm = int(digits[0:2])
            dd = int(digits[2:4])
            yy = int(digits[4:6])
            yyyy = 1900 + yy if yy > 30 else 2000 + yy
            try:
                if 1 <= mm <= 12 and 1 <= dd <= 31:
                    return datetime(yyyy, mm, dd)
            except:
                pass

    # Try common delimited formats
    fmts = [
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%y",
        "%Y%m%d",
        "%m%d%Y",
        "%m%d%y",
    ]

    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except:
            continue

    return None



def add_clean_date_columns(df: pd.DataFrame, date_cols: list) -> pd.DataFrame:
    """
    Create COL_CLEAN for each date column in date_cols.
    DOB_CLEAN must produce age 5–25.
    TESTDATE_CLEAN must be within ~1 year of D_TERM.
    Output format: mm/dd/yyyy
    """
    df = df.copy()

    # Extract term year once
    term_year = df["D_TERM"].apply(_parse_term_to_year)

    today_year = datetime.now().year

    for col in date_cols:
        clean_col = f"{col}_CLEAN"
        out = []

        for raw, term_y in zip(df[col], term_year):
            dt = _safe_parse_date(raw)

            if dt is None:
                out.append(pd.NA)
                continue

            # DOB rules: age 5–25
            if col == "D_DOB":
                age = today_year - dt.year
                if age < 4 or age > 25:
                    out.append(pd.NA)
                    continue

            # TESTDATE rules: within ~1 year of term year
            # if col == "D_TESTDATE":
            #     if term_y is not None:
            #         if abs(dt.year - term_y) > 3:
            #             out.append(pd.NA)
            #             continue

            # Format mm/dd/yyyy
            out.append(dt.strftime("%m/%d/%Y"))

        df[clean_col] = pd.Series(out, dtype="string")

    return df


df_long = add_clean_date_columns(
    df_long,
    date_cols=["D_TESTDATE", "D_DOB"]
)



#----------------------------------------------------------
# CLEAN GRADE
#----------------------------------------------------------
import pandas as pd
import re

def add_clean_grade_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """
    Create COL_CLEAN for grade column.
    Handles:
      - 11th, 3rd, 2nd, 1st
      - 11, 3, 2, 1
      - eleven, three, first, second, etc.
      - K or k → 14
    Output dtype: Int64 (nullable)
    """

    df = df.copy()
    clean_col = f"{col}_CLEAN"

    # Mapping for spelled-out grades
    word_map = {
        "kindergarten": 14,
        "k": 14,
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
        "eleventh": 11,
        "twelfth": 12,
        "thirteenth": 13,
        "fourteen": 14,
        "fifteen": 15,
    }

    cleaned = []

    for raw in df[col]:
        if raw is None or pd.isna(raw):
            cleaned.append(pd.NA)
            continue

        s = str(raw).strip().lower()

        # Remove ordinal suffixes: 1st, 2nd, 3rd, 11th, etc.
        s = re.sub(r"(st|nd|rd|th)$", "", s)

        # If spelled-out word
        if s in word_map:
            cleaned.append(word_map[s])
            continue

        # If numeric
        if re.fullmatch(r"\d+", s):
            cleaned.append(int(s))
            continue

        # If spelled-out number (e.g., "eleven")
        if s in word_map:
            cleaned.append(word_map[s])
            continue

        # If nothing matches → NA
        cleaned.append(pd.NA)

    df[clean_col] = pd.Series(cleaned, dtype="Int64")
    return df


df_long = add_clean_grade_column(df_long, "D_GRADE")



#----------------------------------------------------------
# ORDER OUTPUT COLUMNS
#----------------------------------------------------------
def place_all_clean_columns_next_to_originals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Automatically moves every *_CLEAN column so it appears immediately
    after its original column (same name without _CLEAN).
    """
    df = df.copy()
    cols = list(df.columns)

    # Find all *_CLEAN columns
    clean_cols = [c for c in cols if c.endswith("_CLEAN")]

    for clean in clean_cols:
        original = clean[:-6]  # remove "_CLEAN"

        # If original column doesn't exist, skip
        if original not in cols:
            continue

        # Remove clean column from current position
        cols.remove(clean)

        # Insert clean column right after original
        insert_pos = cols.index(original) + 1
        cols.insert(insert_pos, clean)

    return df[cols]

df_long = place_all_clean_columns_next_to_originals(df_long)



# ---------------------------------------------------------
# Save outputs
# ---------------------------------------------------------

df_wide.to_parquet(DATA_ROOT / "df_wide.parquet", index=False)
df_long.to_parquet(DATA_ROOT / "df_long.parquet", index=False)
