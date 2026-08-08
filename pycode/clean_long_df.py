# -*- coding: utf-8 -*-
"""
Clean df_long for upload:
 - Clean INT columns
 - Clean DATE columns
 - Clean GRADE column
 - Merge settings_xl using SETTINGS_ prefix
 - Filter rows where D_GRADE_CLEAN is in STUDY_GRADES
 
 
 The merged dataframe is the df_long merged to settings by subject
 for each sukbject/mapgrowth_testname combo.  eg. Alg1 may map to math 6+
 for one study and Alg1 for a second study.
 
 the merged_valid dataframe (aka df_long_with_settings) ensures that the
 partner Student Grade is within the STUDY_GRADES from setting of that particular
 study(grades may differ for Alg1 study vs. Math6+ study, for example)
 
 
"""

import re
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
from typing import Optional
import numpy as np

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

# if "df_long" not in globals() or not isinstance(df_long, pd.DataFrame):
#     df_long = pd.read_parquet(Path(DATA_ROOT) / "df_long.parquet")


#==============================================================
# GLOBAL GRADE MAP (used for df_long + settings_xl)
#==============================================================

grade_map = {
    1: ["1", "1ST", "ONE", "FIRST", "GRADE 1", "GRADE 01"],
    2: ["2", "2ND", "TWO", "SECOND", "GRADE 2", "GRADE 02"],
    3: ["3", "3RD", "THREE", "THIRD", "GRADE 3", "GRADE 03"],
    4: ["4", "4TH", "FOUR", "FOURTH", "GRADE 4", "GRADE 04"],
    5: ["5", "5TH", "FIVE", "FIFTH", "GRADE 5", "GRADE 05"],
    6: ["6", "6TH", "SIX", "SIXTH", "GRADE 6", "GRADE 06"],
    7: ["7", "7TH", "SEVEN", "SEVENTH", "GRADE 7", "GRADE 07"],
    8: ["8", "8TH", "EIGHT", "EIGHTH", "GRADE 8", "GRADE 08"],
    9: ["9", "9TH", "NINE", "NINTH", "GRADE 9", "GRADE 09"],
    10: ["10", "10TH", "TEN", "TENTH", "GRADE 10"],
    11: ["11", "11TH", "ELEVEN", "ELEVENTH", "GRADE 11"],
    12: ["12", "12TH", "TWELVE", "TWELFTH", "GRADE 12"],
    # skip 13
    14: ["K", "KINDERGARTEN", "GRADE K"],
}


reverse_map = {}
for num, variants in grade_map.items():
    for v in variants:
        reverse_map[v] = num
        
        
#TODO: add to qa checks early.  and check D_GRADE VS D_GRADE_CLEAN
df_long.D_GRADE.value_counts(dropna = False)




#-----------------------------------------------------------------
# helper function: flag for removal
#-----------------------------------------------------------------
def flag_for_removal(df, rows_to_flag, reason):
    """
    Flags records in df based on rows_to_flag.
    
    - If a row is flagged, append reason to existing FLAG_REASON using '|'.
    - If a row is not flagged, FLAG_REASON becomes NA.
    """

    df = df.copy()

    # Boolean mask for rows to flag
    mask = df.index.isin(rows_to_flag.index)

    # Initialize FLAG_REASON as NA for all rows
    df["FLAG_REASON"] = pd.NA

    # For flagged rows:
    # If FLAG_REASON already exists, append with '|'
    # Otherwise, set to the new reason
    df.loc[mask, "FLAG_REASON"] = (
        df.loc[mask, "FLAG_REASON"]
        .fillna(reason)                      # if NA, set reason
        .astype(str)
        .apply(lambda x: x if x == reason else f"{x}|{reason}")
    )

    return df


def append_flag_reason(df, mask, reason):
    """
    Append a reason to FLAG_REASON.

    If FLAG_REASON is null:
        reason

    If FLAG_REASON already contains a reason:
        existing_reason|reason
    """

    current = df.loc[mask, "FLAG_REASON"]

    df.loc[mask, "FLAG_REASON"] = np.where(
        current.isna(),
        reason,
        current.astype(str) + "|" + reason
    )

    return df


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
    cols=["D_LOCAL_STID", "D_STATE_STID", "D_AGENCYCODE", "D_SS", "D_PLCODE"
          ]
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
    return df, cleaned


df_long, cleaned = add_clean_grade_column(df_long, "D_GRADE")



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

df_long[['D_GRADE','D_GRADE_CLEAN']].value_counts(dropna = False)


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



# ================================================================
# 1. MERGE ON SUBJECT (LEFT MERGE TO DETECT DROPPED SUBJECTS)
# ================================================================

merged = df_long.merge(
    settings_prefixed,
    left_on="D_SUBJECT",
    right_on="SETTINGS_D_SUBJECT",
    how="left",
    indicator=True
)

# Rows missing in settings (subject not found)
merged_dropped_subjects = merged[merged["_merge"] == "left_only"].copy()

# Rows that matched settings (inner behavior)
merged_inner = merged[merged["_merge"] == "both"].copy()

# Remove merge indicator
merged_inner.drop(columns=["_merge"], inplace=True)
merged_dropped_subjects.drop(columns=["_merge"], inplace=True)



# ================================================================
# 3. FLAG RECORDS FOR REMOVAL
# ================================================================

merged_inner["FLAG_REASON"] = pd.NA


# ----------------------------------------------------
# FLAG MISSING GRADE
# ----------------------------------------------------
missing_grade_mask = merged_inner["D_GRADE_CLEAN"].isna()

merged_inner = append_flag_reason(
    merged_inner,
    missing_grade_mask,
    "missing_grade"
)


# ----------------------------------------------------
# FLAG GRADE NOT IN ANY STUDY FOR SUBJECT
# ----------------------------------------------------
# Build a lookup of all grades valid for a subject
# across all studies.

allowed_grades_by_subject = (
    settings_prefixed
    .groupby("SETTINGS_D_SUBJECT")["SETTINGS_GRADE_LIST"]
    .apply(
        lambda x: {
            int(g)
            for grade_list in x.dropna()
            for g in grade_list
        }
    )
    .to_dict()
)


grade_allowed_any_study = []

for subject, grade in zip(
    merged_inner["D_SUBJECT"],
    merged_inner["D_GRADE_CLEAN"]
):

    if pd.isna(subject):
        grade_allowed_any_study.append(False)

    elif pd.isna(grade):
        grade_allowed_any_study.append(False)

    elif subject not in allowed_grades_by_subject:
        grade_allowed_any_study.append(False)

    else:
        grade_allowed_any_study.append(
            int(grade)
            in allowed_grades_by_subject[subject]
        )

merged_inner["GRADE_ALLOWED_ANY_STUDY"] = grade_allowed_any_study


off_grade_mask = (
    merged_inner["D_GRADE_CLEAN"].notna()
    & ~merged_inner["GRADE_ALLOWED_ANY_STUDY"]
)

merged_inner = append_flag_reason(
    merged_inner,
    off_grade_mask,
    "grade_not_in_study"
)


# ----------------------------------------------------
# CREATE FLAGGED FOR REMOVAL TABLE
# ----------------------------------------------------
flagged_for_removal = merged_inner.loc[
    merged_inner["FLAG_REASON"].notna()
].copy()


# ----------------------------------------------------
# REMOVE FLAGGED RECORDS BEFORE STUDY FILTERING
# ----------------------------------------------------
merged_inner = merged_inner.loc[
    merged_inner["FLAG_REASON"].isna()
].copy()

# TODO:  ADD LOGIC TO FLAG ANY GRADE THAT IS OUTSIDE RANGE OF 
        #  ANY STUDY BASED ON THE SUBJECT.  EG. MATH GRADE 2
        # NOT VALID FOR EITHER MAP 2-5 OR 6+ OR EOC STUDY.


# ================================================================
# 4. FILTER ROWS WHERE GRADE IS ALLOWED
# ================================================================

merged_inner["GRADE_ALLOWED"] = merged_inner.apply(
    lambda r: (
        pd.notna(r["D_GRADE_CLEAN"]) and
        isinstance(r["SETTINGS_GRADE_LIST"], (list, tuple)) and
        r["D_GRADE_CLEAN"] in r["SETTINGS_GRADE_LIST"]
    ),
    axis=1
)

# Valid rows
merged_valid = merged_inner[merged_inner["GRADE_ALLOWED"]].copy()


# ================================================================
# 5. CLEAN SETTINGS_STUDY_GRADES
# ================================================================

merged_valid["SETTINGS_STUDY_GRADES"] = (
    merged_valid["SETTINGS_STUDY_GRADES"]
    .apply(lambda x: None if pd.isna(x) else str(x).strip())
)


# ================================================================
# 6. INVALID ROWS FOR QA
# ================================================================

keep_cols = [
    "D_DISTRICTNAME",
    "D_SCHOOLNAME",
    "D_FILENAMEFROMDISTRICT",
    "D_SUBJECT",
    "SETTINGS_D_MAPGROWTH_TEST_NAME",
    "D_GRADE",
    "D_GRADE_CLEAN",
    "SETTINGS_STUDY_GRADES",
    "FLAG_REASON"
]

merged_invalid = merged_inner.loc[
    ~merged_inner["GRADE_ALLOWED"],
    [c for c in keep_cols if c in merged_inner.columns]
].copy()


flagged_for_removal = flagged_for_removal[
    [c for c in keep_cols if c in flagged_for_removal.columns]
].copy()


# ================================================================
# 7. FINAL CLEANUP
# ================================================================

df_long = merged_valid.drop(columns=["SETTINGS_NOTES",'GRADE_ALLOWED_ANY_STUDY', 'GRADE_ALLOWED']
                            , errors="ignore")


def sanitize_object_columns(df):
    df = df.copy()

    def sanitize_value(x):
        # None / NaN
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None

        # numpy arrays or python lists → convert to string
        if isinstance(x, (list, tuple, np.ndarray)):
            return str(list(x))  # convert ndarray → list → string

        # everything else → convert to string
        return str(x).strip()

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].apply(sanitize_value)

    return df


settings_prefixed = sanitize_object_columns(settings_prefixed)
merged_invalid = sanitize_object_columns(merged_invalid)
flagged_for_removal = sanitize_object_columns(flagged_for_removal)
df_long = sanitize_object_columns(df_long)


#==============================================================
# SAVE OUTPUT
#  df_long -- long file with settings added.  reduced to 
#             valid grades.         
#  merged_valid -- df_long with Settings_XL fields
#==============================================================

df_wide.to_parquet(
    DATA_ROOT / "df_wide.parquet", 
    index=False
    )

df_long.to_parquet(
    DATA_ROOT / "df_long.parquet",
    index=False
)

 
# df_long_with_settings.to_parquet(
#     DATA_ROOT / "df_long_with_settings.parquet",
#     index=False
# )

settings_prefixed.to_parquet(
    DATA_ROOT / "settings_prefixed.parquet",
    index=False
)

# merged_invalid.to_parquet(
#     DATA_ROOT / "merged_invalid.parquet",
#     index=False
# )

flagged_for_removal.to_parquet(
    DATA_ROOT / "flagged_for_removal.parquet",
    index=False
)



