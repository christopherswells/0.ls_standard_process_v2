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


#spyder seems to get screwy with the wd sometimes
ROOT = Path(__file__).resolve().parents[1]   # goes up from pycode → repo root
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
    
from pycode.settings import COMBINED_FILE

SUFFIXES = ["SS", "PLCODE", "PLDESC", "TESTNAME", "TESTDATE", "RETEST"]

def pivot_scores_long_no_impute(
    combineddf: pd.DataFrame,
    drop_rows_missing_ss: bool = False,
    drop_rows_all_scores_missing: bool = True,
) -> pd.DataFrame:
    """
    Wide -> long without imputation:
      - Score fields are columns that end with _{SS,PLCODE,PLDESC,TESTNAME,TESTDATE,RETEST}
      - SUBJECT = part before the last underscore
      - Output = all NON-subject fields + SUBJECT + the 6 score fields (blank/NA if not present)

    Parameters
    ----------
    combineddf : pd.DataFrame
        Wide combined data.
    drop_rows_missing_ss : bool
        If True, drop rows where SS is missing (like your previous dropna on SS).
    drop_rows_all_scores_missing : bool
        If True, drop rows where all 6 score fields are missing/blank.

    Returns
    -------
    pd.DataFrame
        Long dataframe.
    """
    df = combineddf.copy()

    # 1) Identify subject score columns strictly by suffix
    suffix_pattern = re.compile(rf"^(?P<subject>.+)_(?P<suffix>{'|'.join(SUFFIXES)})$", re.IGNORECASE)

    score_cols: List[str] = []
    subjects: List[str] = []
    col_to_suffix: dict = {}  # col -> (subject, suffix_upper)

    for c in df.columns:
        m = suffix_pattern.match(str(c))
        if m:
            score_cols.append(c)
            subj = m.group("subject")
            suf = m.group("suffix").upper()
            col_to_suffix[c] = (subj, suf)
            subjects.append(subj)

    subjects = sorted(pd.unique(subjects))
    non_subject_fields = [c for c in df.columns if c not in score_cols]

    # 2) Build long df by looping subjects (your approach), but standardized
    long_parts = []
    for subj in subjects:
        subject_cols = [c for c in score_cols if col_to_suffix[c][0] == subj]

        temp = df[non_subject_fields + subject_cols].copy()
        temp["SUBJECT"] = subj

        # Rename subject columns to just the suffix (SS, TESTNAME, etc.)
        rename_map = {c: col_to_suffix[c][1] for c in subject_cols}
        temp = temp.rename(columns=rename_map)

        # Ensure all expected suffix columns exist (no imputation; create missing as NA)
        for suf in SUFFIXES:
            if suf not in temp.columns:
                temp[suf] = pd.NA

        # Optional: reorder score columns consistently
        temp = temp[non_subject_fields + ["SUBJECT"] + SUFFIXES]

        long_parts.append(temp)

    if not long_parts:
        # No score columns found: return base + empty score columns
        out = df[non_subject_fields].copy()
        out["SUBJECT"] = pd.NA
        for suf in SUFFIXES:
            out[suf] = pd.NA
        return out

    long_df = pd.concat(long_parts, ignore_index=True)

    # 3) Clean blank strings -> NA for score fields only
    long_df[SUFFIXES] = long_df[SUFFIXES].replace(r"^\s*$", pd.NA, regex=True)

    # 4) Drop rules (match your prior behavior as options)
    if drop_rows_all_scores_missing:
        long_df = long_df.dropna(subset=SUFFIXES, how="all")

    if drop_rows_missing_ss:
        long_df = long_df.dropna(subset=["SS"])

    # 5) Rename to your requested final column names (SS already SS, etc.)
    # (You asked for TESTNAME, SS, PLDESC, PLCODE, TESTDATE, RETEST, SUBJECT)
    # Already matches.

    return long_df

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


if "combinedDf" in globals() and isinstance(combinedDf, pd.DataFrame):
    df_wide = combinedDf
else:
    df_wide = pd.read_excel(COMBINED_FILE, dtype=str, engine="openpyxl")
    df_wide = _normalize_strings(df_wide)

long_df = pivot_scores_long_no_impute(
    df_wide,
    drop_rows_missing_ss=False,          # set True to mimic your dropna(subset=['SS'])
    drop_rows_all_scores_missing=True    # usually what you want
)

long_df.shape
