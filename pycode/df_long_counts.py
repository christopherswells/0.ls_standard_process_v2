# -*- coding: utf-8 -*-
"""
Created on Tue Jun  9 20:35:24 2026

@author: Chris.Wells
"""

import pandas as pd
import numpy as np
from typing import List, Optional

from pycode.settings import *

# deciding what reports to keep. will move helper functions later
from common.ls_map_count_functions import missingness_long


# -----------------------------------------------------
# RE-IMPORT DATA
# -----------------------------------------------------
df_long = pd.read_parquet(DATA_ROOT / "df_long.parquet")
df_wide = pd.read_parquet(DATA_ROOT / "df_wide.parquet")


# ----------------------------------------------------
# MISSINGNESS OF DF_WIDE
# ----------------------------------------------------
missing_by_grade_and_file = missingness_long(
    df=df_wide,
    group_cols=["GRADE", "FILENAMEFROMDISTRICT"]
)

missing_by_file_only = missingness_long(
    df=df_wide,
    group_cols=["FILENAMEFROMDISTRICT"]
)

flagged_for_removal = pd.read_parquet(
    DATA_ROOT / "flagged_for_removal.parquet"
)


# ----------------------------------------------------
# MISSINGNESS OF DF_LONG
# ----------------------------------------------------
missing_long_by_grade_and_file = missingness_long(
    df=df_long,
    group_cols=["D_GRADE_CLEAN", "D_FILENAMEFROMDISTRICT"]
)

missing_long_by_file_only = missingness_long(
    df=df_long,
    group_cols=["D_FILENAMEFROMDISTRICT"]
)


# ----------------------------------------------------
# COUNTS SUBJECT
# ----------------------------------------------------
counts_subject = (
    df_long
    .groupby(["D_SUBJECT"], dropna=False)
    .size()
    .rename("record_count")
    .reset_index()
    .sort_values(["D_SUBJECT"])
)


# ----------------------------------------------------
# COUNTS SUBJECT / GRADE
# ----------------------------------------------------
counts_subject_grade = (
    df_long
    .groupby(["D_SUBJECT", "D_GRADE_CLEAN"], dropna=False)
    .size()
    .rename("record_count")
    .reset_index()
    .sort_values(["D_GRADE_CLEAN", "D_SUBJECT"])
)


# ----------------------------------------------------
# FLAGGED FOR REMOVAL SUMMARY
# ----------------------------------------------------

summary_parts = []

for reason, df_reason in flagged_for_removal.groupby(
    "FLAG_REASON",
    dropna=False
):

    # base grouping
    group_cols = [
        "FLAG_REASON",
        "D_FILENAMEFROMDISTRICT"
    ]

    # add fields relevant to each flag
    if "grade_not_in_study" in str(reason):
        group_cols.extend([
            "D_SUBJECT",
            "D_GRADE",
            "D_GRADE_CLEAN"
        ])

    if "missing_grade" in str(reason):
        group_cols.extend([
            "D_SUBJECT",
            "D_GRADE"
        ])

    if "non_numeric_SS" in str(reason):
        group_cols.extend([
            "D_SUBJECT",
            "D_SS"
        ])

    if "incorrect_term" in str(reason):
        group_cols.extend([
            "D_TERM",
            "SETTINGS_TERM"
        ])

    if "test_date_out_of_range" in str(reason):
        group_cols.extend([
            "D_TESTDATE",
            "D_TESTDATE_CLEAN",
            "SETTINGS_TERM"
        ])

    # keep only existing columns
    group_cols = [
        c for c in group_cols
        if c in df_reason.columns
    ]

    temp = (
        df_reason
        .groupby(group_cols, dropna=False)
        .size()
        .rename("record_count")
        .reset_index()
    )

    summary_parts.append(temp)

flagged_for_removal_summary = pd.concat(
    summary_parts,
    ignore_index=True
)


flagged_for_removal_summary = (
    flagged_for_removal_summary
    .sort_values(
        [
            "FLAG_REASON",
            "D_FILENAMEFROMDISTRICT"
        ]
    )
)


# ----------------------------------------------------
# OUTPUT COUNTS AND QA
# ----------------------------------------------------

def move_col_to_end(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """
    Move a column to the end of the dataframe if present.
    """
    if col not in df.columns:
        return df

    cols = [c for c in df.columns if c != col] + [col]
    return df[cols]


summaries = {
    "missing_wide_by_file_only": missing_by_file_only,
    "missing_wide_by_grade_and_file": missing_by_grade_and_file,
    "missing_long_by_file_only": missing_long_by_file_only,
    "missing_long_by_grade_and_file": missing_long_by_grade_and_file,
    "counts_subject": counts_subject,
    "counts_subject_grade": counts_subject_grade,
    "flagged_for_removal_summary": flagged_for_removal_summary,
}


# ----------------------------------------------------
# MOVE FILENAME COLUMN TO END FOR READABILITY
# ----------------------------------------------------
for name, df in summaries.items():

    if "FILENAMEFROMDISTRICT" in df.columns:
        summaries[name] = move_col_to_end(
            df,
            "FILENAMEFROMDISTRICT"
        )

    elif "D_FILENAMEFROMDISTRICT" in df.columns:
        summaries[name] = move_col_to_end(
            df,
            "D_FILENAMEFROMDISTRICT"
        )


# ----------------------------------------------------
# OUTPUT
# ----------------------------------------------------
output_to_excel_tab(
    outputDict=summaries,
    outpath=str(OUT_PARTNER_COUNTS_TS)
)
