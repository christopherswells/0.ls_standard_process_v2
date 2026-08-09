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
from datetime import datetime
from pathlib import Path
import numpy as np

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

df_long = df_long.reset_index(drop=True)

# ---------------------------------------------------------
# Rename long columns with prefix (already uppercase)
# ---------------------------------------------------------

df_long = rename_columns_upper_with_prefix(df_long)







#================================================================================================================
# PREVIOUSLY FROM CLEAN_LONG_DF.PY
# JOINING TO REDUCE PARQUET OUTPUT
#================================================================================================================

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
# ADD *_CLEAN column coerced to Int64
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
    # cols=["D_LOCAL_STID", "D_STATE_STID", "D_AGENCYCODE", "D_SS", "D_PLCODE" ]
    cols=["D_LOCAL_STID", "D_STATE_STID", "D_AGENCYCODE", "D_SS" ]
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

    # df[clean_col] = pd.Series(cleaned, dtype="Int64")
    df[clean_col] = cleaned
    df[clean_col] = df[clean_col].astype("Int64")
    return df, cleaned


df_long, cleaned = add_clean_grade_column(df_long, "D_GRADE")

print(
    df_long[
        ["D_GRADE", "D_GRADE_CLEAN"]
    ]
    .drop_duplicates()
    .sort_values(["D_GRADE"])
)



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
# 1. MERGE SETTINGS ON SUBJECT/GRADE 
#    (LEFT MERGE TO DETECT DROPPED SUBJECTS)
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
# 3. FLAG RECORDS FOR REMOVAL and reset index
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
# FLAG NON-NUMERIC SS
# ----------------------------------------------------
# D_SS contains a value but could not be converted
# to D_SS_CLEAN.

non_numeric_ss_mask = (
    merged_inner["D_SS"].notna()
    & merged_inner["D_SS"].astype(str).str.strip().ne("")
    & merged_inner["D_SS_CLEAN"].isna()
)

merged_inner = append_flag_reason(
    merged_inner,
    non_numeric_ss_mask,
    "non_numeric_SS"
)



# ----------------------------------------------------
# FLAG INCORRECT TERM
# ----------------------------------------------------

def is_incorrect_term(d_term, settings_term):
    """
    Flag if:
      - term contains a year different from study year
      - term explicitly indicates Fall/Summer/Winter

    Do NOT flag:
      - blanks
      - unrecognized strings
      - Spring without a year
    """

    if pd.isna(d_term) or pd.isna(settings_term):
        return False

    d_term = str(d_term).upper().strip()
    settings_term = str(settings_term).strip()

    # study year comes from SETTINGS_TERM (e.g. 202502)
    m = re.match(r"^(\d{4})", settings_term)

    if not m:
        return False

    study_year = int(m.group(1))

    # --------------------------------------------------
    # Explicit season detection
    # --------------------------------------------------

    spring_patterns = [
        r"\bSPRING\b",
        r"\bSPR\b",
        r"\bSP\b",
    ]

    fall_patterns = [
        r"\bFALL\b",
        r"\bAUTUMN\b",
        r"\bFA\b",
        r"\bF\d{2}\b",
    ]

    summer_patterns = [
        r"\bSUMMER\b",
        r"\bSUM\b",
        r"\bSU\b",
    ]

    winter_patterns = [
        r"\bWINTER\b",
        r"\bWIN\b",
        r"\bWI\b",
        r"\bW\d{2}\b",
    ]

    if any(re.search(p, d_term) for p in fall_patterns):
        return True

    if any(re.search(p, d_term) for p in summer_patterns):
        return True

    if any(re.search(p, d_term) for p in winter_patterns):
        return True

    # --------------------------------------------------
    # YEAR DETECTION
    # --------------------------------------------------

    years_found = []

    # 4-digit years
    years_found.extend(
        [
            int(x)
            for x in re.findall(r"\b20\d{2}\b", d_term)
        ]
    )

    # embedded forms like SPR2025
    years_found.extend(
        [
            int(x)
            for x in re.findall(r"20\d{2}", d_term)
        ]
    )

    # short forms like F25 / SP25 / W25
    years_found.extend(
        [
            2000 + int(x)
            for x in re.findall(r"(?<!\d)(\d{2})(?!\d)", d_term)
            if 0 <= int(x) <= 50
        ]
    )

    years_found = list(set(years_found))

    if years_found:

        if study_year not in years_found:

            # allow school year notation such as 2024-25
            if (
                study_year in years_found
                or study_year - 1 in years_found
            ):
                pass
            else:
                return True

    return False


incorrect_term_mask = [
    is_incorrect_term(d_term, settings_term)
    for d_term, settings_term in zip(
        merged_inner["D_TERM"],
        merged_inner["SETTINGS_TERM"]
    )
]

merged_inner = append_flag_reason(
    merged_inner,
    incorrect_term_mask,
    "incorrect_term"
)



# ----------------------------------------------------
# FLAG TEST DATE OUT OF RANGE
# ----------------------------------------------------

def is_test_date_out_of_range(test_date, settings_term):

    if pd.isna(test_date) or pd.isna(settings_term):
        return False

    try:
        test_dt = pd.to_datetime(test_date)
    except Exception:
        return False

    settings_term = str(settings_term).strip()

    m = re.match(r"^(\d{4})", settings_term)

    if not m:
        return False

    study_year = int(m.group(1))

    valid_start = pd.Timestamp(study_year, 2, 1)
    valid_end = pd.Timestamp(study_year, 6, 30)

    return (
        test_dt < valid_start
        or test_dt > valid_end
    )


test_date_out_of_range_mask = [
    is_test_date_out_of_range(test_date, settings_term)
    for test_date, settings_term in zip(
        merged_inner["D_TESTDATE_CLEAN"],
        merged_inner["SETTINGS_TERM"]
    )
]

merged_inner = append_flag_reason(
    merged_inner,
    test_date_out_of_range_mask,
    "test_date_out_of_range"
)





# ----------------------------------------------------
# CREATE FLAGGED FOR REMOVAL TABLE
# ----------------------------------------------------
flagged_for_removal = (merged_inner.loc[
        merged_inner["FLAG_REASON"].notna()]
            .copy()
            .reset_index(drop = True)
)
# Move FLAG_REASON to first column
if "FLAG_REASON" in flagged_for_removal.columns:
    flag_reason = flagged_for_removal.pop("FLAG_REASON")
    flagged_for_removal.insert(0, "FLAG_REASON", flag_reason)


# ----------------------------------------------------
# REMOVE FLAGGED RECORDS BEFORE STUDY FILTERING
# ----------------------------------------------------
merged_inner = merged_inner.loc[
    merged_inner["FLAG_REASON"].isna()
].copy()


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
merged_valid = (
    merged_inner[
        merged_inner["GRADE_ALLOWED"]
    ]
    .copy()
    .reset_index(drop=True)
)


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
].copy().reset_index(drop=True)


# flagged_for_removal = flagged_for_removal[
#     [c for c in keep_cols if c in flagged_for_removal.columns]
# ].copy()


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

