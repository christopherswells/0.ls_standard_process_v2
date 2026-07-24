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

# ---------------------------------------------------------
# Save outputs
# ---------------------------------------------------------

df_wide.to_parquet(DATA_ROOT / "df_wide.parquet", index=False)
df_long.to_parquet(DATA_ROOT / "df_long.parquet", index=False)
