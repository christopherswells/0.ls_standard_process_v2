# -*- coding: utf-8 -*-
"""
Clean df_long for upload:
 - Clean INT columns
 - Clean DATE columns
 - Clean GRADE column
 - Merge settings_xl using SETTINGS_ prefix
 - Filter rows where D_GRADE_CLEAN is in STUDY_GRADES
"""

import re
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
from typing import Optional

#---------------------------------------------------
# SETUP
#---------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pycode.settings import *   # loads DATA_ROOT and settings_xl


#---------------------------------------------------
# LOAD DF_LONG
#---------------------------------------------------

if "df_long" not in globals() or not isinstance(df_long, pd.DataFrame):
    df_long = pd.read_parquet(Path(DATA_ROOT) / "df_long.parquet")


#==============================================================
# GLOBAL GRADE MAP (used for df_long + settings_xl)
#==============================================================

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
    # skip 13
    14: ["K", "KINDERGARTEN"],
}

reverse_map = {}
for num, variants in grade_map.items():
    for v in variants:
        reverse_map[v] = num


#==============================================================
# CLEAN INT COLUMNS
#==============================================================

def add_clean_int_columns(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    df = df.copy()
    for col in cols:
        clean_col = f"{col}_CLEAN"
        series = df[col].replace(r"^\s*$", pd.NA, regex=True)
        df[clean_col] = pd.to_numeric(series, errors="coerce").astype("Int64")
    return df

df_long = add_clean_int_columns(
    df_long,
    cols=["D_LOCAL_STID", "D_STATE_STID", "D_AGENCYCODE", "D_SS", "D_PLCODE"]
)


#==============================================================
# CLEAN DATE COLUMNS
#==============================================================

def _parse_term_to_year(term: str) -> Optional[int]:
    if term is None or pd.isna(term):
        return None
    m = re.search(r"(\d{4})", str(term))
    return int(m.group(1)) if m else None


def _safe_parse_date(raw: str) -> Optional[datetime]:
    if raw is None or pd.isna(raw):
        return None

    s = str(raw).strip()
    s = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?$", "", s)

    # digits-only formats
    if re.fullmatch(r"\d+", s):
        digits = s

        # 8-digit mmddyyyy or yyyymmdd
        if len(digits) == 8:
            mm = int(digits[0:2])
            dd = int(digits[2:4])
            yyyy = int(digits[4:8])
            try:
                if 1 <= mm <= 12 and 1 <= dd <= 31:
                    return datetime(yyyy, mm, dd)
            except:
                pass

            yyyy2 = int(digits[0:4])
            mm2 = int(digits[4:6])
            dd2 = int(digits[6:8])
            try:
                if 1 <= mm2 <= 12 and 1 <= dd2 <= 31:
                    return datetime(yyyy2, mm2, dd2)
            except:
                pass

        # 7-digit mddyyyy
        if len(digits) == 7:
            mm = int(digits[0])
            dd = int(digits[1:3])
            yyyy = int(digits[3:7])
            try:
                if 1 <= mm <= 12 and 1 <= dd <= 31:
                    return datetime(yyyy, mm, dd)
            except:
                pass

        # 6-digit mmddyy
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

    # common formats
    fmts = [
        "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%Y/%m/%d",
        "%m/%d/%y", "%Y%m%d", "%m%d%Y", "%m%d%y"
    ]

    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except:
            continue

    return None


def add_clean_date_columns(df: pd.DataFrame, date_cols: list) -> pd.DataFrame:
    df = df.copy()
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

            # DOB age rule
            if col == "D_DOB":
                age = today_year - dt.year
                if age < 4 or age > 25:
                    out.append(pd.NA)
                    continue

            out.append(dt.strftime("%m/%d/%Y"))

        df[clean_col] = pd.Series(out, dtype="string")

    return df


df_long = add_clean_date_columns(df_long, ["D_TESTDATE", "D_DOB"])


#==============================================================
# CLEAN GRADE COLUMN
#==============================================================

def add_clean_grade_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df = df.copy()
    clean_col = f"{col}_CLEAN"

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


#==============================================================
# PLACE *_CLEAN COLUMNS NEXT TO ORIGINALS
#==============================================================

def place_all_clean_columns_next_to_originals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cols = list(df.columns)
    clean_cols = [c for c in cols if c.endswith("_CLEAN")]

    for clean in clean_cols:
        original = clean[:-6]
        if original not in cols:
            continue
        cols.remove(clean)
        insert_pos = cols.index(original) + 1
        cols.insert(insert_pos, clean)

    return df[cols]

df_long = place_all_clean_columns_next_to_originals(df_long)


#==============================================================
# MERGE SETTINGS to make merged_valid dataframe with Settings
#==============================================================

def parse_study_grades(raw):
    if raw is None or pd.isna(raw):
        return []

    s = str(raw).upper().strip()
    tokens = re.split(r"[,\s;]+", s)
    out = []

    for t in tokens:
        if not t:
            continue

        # ranges like 3-5
        if "-" in t:
            a, b = t.split("-", 1)
            a = a.strip()
            b = b.strip()
            if a in reverse_map and b in reverse_map:
                lo = reverse_map[a]
                hi = reverse_map[b]
                out.extend(range(lo, hi + 1))
            continue

        # direct lookup
        if t in reverse_map:
            out.append(reverse_map[t])

    return sorted(set(out))


# prefix settings columns
settings_prefixed = settings_xl.rename(columns=lambda c: f"SETTINGS_{c}")

# expand STUDY_GRADES
settings_prefixed["SETTINGS_GRADE_LIST"] = (
    settings_prefixed["SETTINGS_STUDY_GRADES"].apply(parse_study_grades)
)

# merge
merged = df_long.merge(
    settings_prefixed,
    left_on=["D_SUBJECT", "D_STATE"],
    right_on=["SETTINGS_D_SUBJECT", "SETTINGS_STATE"],
    how="left"
)

# filter rows where grade is allowed
merged["GRADE_ALLOWED"] = merged.apply(
    lambda r: r["D_GRADE_CLEAN"] in r["SETTINGS_GRADE_LIST"]
    if isinstance(r["SETTINGS_GRADE_LIST"], list)
    else False,
    axis=1
)

merged_valid = merged[merged["GRADE_ALLOWED"]]


# makes settings grades string
merged_valid["SETTINGS_STUDY_GRADES"] = (
    merged_valid["SETTINGS_STUDY_GRADES"]
    .apply(lambda x: None if pd.isna(x) else str(x).strip())
)


# drop notes
df_long_with_settings = merged_valid.drop(columns=["SETTINGS_NOTES"], errors="ignore")




#==============================================================
# SAVE OUTPUT
#  df_long -- long file without SETTINGS_XL fields merged in
#  merged_valid -- df_long with Settings_XL fields
#==============================================================

df_long.to_parquet(DATA_ROOT / "df_long.parquet", index=False)
df_long_with_settings.to_parquet(DATA_ROOT / "df_long_with_settings.parquet", index=False)
