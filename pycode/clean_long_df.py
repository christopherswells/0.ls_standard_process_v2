# -*- coding: utf-8 -*-
"""
Created on Fri Jul 24 15:39:20 2026

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


#---------------------------------------------------
# IMPORT DF_LONG IF NOT ALREADY LOADED
#---------------------------------------------------
if "df_long" in globals() and isinstance(df_long, pd.DataFrame):
    pass
else:
    df_long = pd.read_parquet(Path(DATA_ROOT) / "df_long.parquet")
    


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

def add_clean_grade_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df = df.copy()
    clean_col = f"{col}_CLEAN"

    grade_map = {
        1: ["1", "1ST", "ONE", "FIRST"],
        2: ["2", "2ND", "TWO", "SECOND"],
        3: ["3", "3RD", "THREE", "THIRD"],
        4: ["4", "4TH", "FOUR", "FOURTH"],
        5: ["5", "5TH", "FIVE", "FIFTH"],
        6: ["6", "6TH", "SIX", "SIXTH"],
        7: ["7", "7TH", "SEVEN", "SEVENTH"],
        8: ["8", "8TH", "EIGHT", "EIGHTH"],
        9: ["9", "9TH", "NINE", "NINTH"],
        10: ["10", "10TH", "TEN", "TENTH"],
        11: ["11", "11TH", "ELEVEN", "ELEVENTH"],
        12: ["12", "12TH", "TWELVE", "TWELFTH"],
        14: ["K", "KINDERGARTEN"],
    }

    reverse_map = {}
    for num, variants in grade_map.items():
        for v in variants:
            reverse_map[v] = num

    cleaned = []
    for raw in df[col]:
        if raw is None or pd.isna(raw):
            cleaned.append(pd.NA)
            continue

        s = str(raw).strip().upper()

        cleaned.append(reverse_map.get(s, pd.NA))

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

# df_wide.to_parquet(DATA_ROOT / "df_wide.parquet", index=False)
df_long.to_parquet(DATA_ROOT / "df_long.parquet", index=False)