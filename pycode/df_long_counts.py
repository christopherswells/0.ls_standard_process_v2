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
# REMOVE UNWANTED RECORDS FROM LONG MISSINGNESS REPORTS
# ----------------------------------------------------
def remove_unwanted_long_missingness_rows(
    df: pd.DataFrame
) -> pd.DataFrame:
    """
    Remove missingness records where col_name:
      - equals D_MNAME
      - equals FLAG_REASON
      - starts with SETTINGS
    """
    col_name_clean = (
        df["col_name"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    unwanted_mask = (
        col_name_clean.isin([
            "D_MNAME",
            "FLAG_REASON",
        ])
        | col_name_clean.str.startswith(
            "SETTINGS",
            na=False
        )
    )

    return (
        df.loc[~unwanted_mask]
        .copy()
        .reset_index(drop=True)
    )


missing_long_by_file_only = (
    remove_unwanted_long_missingness_rows(
        missing_long_by_file_only
    )
)

missing_long_by_grade_and_file = (
    remove_unwanted_long_missingness_rows(
        missing_long_by_grade_and_file
    )
)


# ----------------------------------------------------
# FLAGGED LONG MISSINGNESS (>5%)
# ----------------------------------------------------
missing_long_flagged = (
    missing_long_by_file_only
    .loc[
        missing_long_by_file_only["missing_percentage"] > 5
    ]
    .sort_values(
        [
            "D_FILENAMEFROMDISTRICT",
            "missing_percentage",
        ],
        ascending=[True, False]
    )
    .copy()
    .reset_index(drop=True)
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
# COUNTS DISTRICT / SUBJECT
# ----------------------------------------------------
counts_by_district = (
    df_long
    .groupby(
        ["D_FILENAMEFROMDISTRICT", "D_SUBJECT"],
        dropna=False
    )
    .size()
    .rename("record_count")
    .reset_index()
    .sort_values(
        ["D_FILENAMEFROMDISTRICT", "D_SUBJECT"]
    )
)


# ----------------------------------------------------
# COUNTS DISTRICT / SUBJECT / GRADE
# ----------------------------------------------------
counts_by_district_grade = (
    df_long
    .groupby(
        [
            "D_FILENAMEFROMDISTRICT",
            "D_SUBJECT",
            "D_GRADE_CLEAN"
        ],
        dropna=False
    )
    .size()
    .rename("record_count")
    .reset_index()
    .sort_values(
        [
            "D_FILENAMEFROMDISTRICT",
            "D_SUBJECT",
            "D_GRADE_CLEAN"
        ]
    )
)


# ----------------------------------------------------
# FLAGGED FOR REMOVAL SUMMARY
# ----------------------------------------------------

summary_parts = []

for reason, df_reason in flagged_for_removal.groupby(
    "FLAG_REASON",
    dropna=False
):

    # Base grouping included for every flag
    group_cols = [
        "FLAG_REASON",
        "D_FILENAMEFROMDISTRICT",
        "D_SUBJECT",
    ]

    # Add fields specific to the flag type
    if "grade_not_in_study" in str(reason):
        group_cols.extend([
            "D_GRADE",
            "D_GRADE_CLEAN"
        ])

    if "missing_grade" in str(reason):
        group_cols.extend([
            "D_GRADE"
        ])

    if "non_numeric_SS" in str(reason):
        group_cols.extend([
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

    # Keep only columns that exist
    group_cols = [
        c for c in group_cols
        if c in df_reason.columns
    ]

    # Remove duplicate grouping columns while preserving order
    group_cols = list(dict.fromkeys(group_cols))

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


# ----------------------------------------------------
# TOTAL PARTNER RECORDS BY FILE / SUBJECT
# ----------------------------------------------------
subject_totals = (
    df_long
    .groupby(
        [
            "D_FILENAMEFROMDISTRICT",
            "D_SUBJECT"
        ],
        dropna=False
    )
    .size()
    .rename("total_partner_subject_records")
    .reset_index()
)


# ----------------------------------------------------
# ADD TOTALS AND PERCENTAGES
# ----------------------------------------------------
flagged_for_removal_summary = (
    flagged_for_removal_summary
    .merge(
        subject_totals,
        on=[
            "D_FILENAMEFROMDISTRICT",
            "D_SUBJECT"
        ],
        how="left"
    )
)

flagged_for_removal_summary["pct_affected_records"] = (
    100
    * flagged_for_removal_summary["record_count"]
    / flagged_for_removal_summary["total_partner_subject_records"]
)

flagged_for_removal_summary["pct_affected_records"] = (
    flagged_for_removal_summary["pct_affected_records"]
    .round(1)
)


# ----------------------------------------------------
# PLACE TOTAL / COUNT / PCT TOGETHER
# ----------------------------------------------------
base_cols = [
    c for c in flagged_for_removal_summary.columns
    if c not in [
        "total_partner_subject_records",
        "record_count",
        "pct_affected_records",
    ]
]

flagged_for_removal_summary = flagged_for_removal_summary[
    base_cols
    + [
        "total_partner_subject_records",
        "record_count",
        "pct_affected_records",
    ]
]


# ----------------------------------------------------
# SORT FOR READABILITY
# ----------------------------------------------------
sort_cols = [
    c for c in [
        "FLAG_REASON",
        "D_FILENAMEFROMDISTRICT",
        "D_SUBJECT"
    ]
    if c in flagged_for_removal_summary.columns
]

flagged_for_removal_summary = (
    flagged_for_removal_summary
    .sort_values(sort_cols)
    .reset_index(drop=True)

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
    # ------------------------------------------------
    # PRIORITY OUTPUTS
    # ------------------------------------------------
    "flagged_for_removal_summary": flagged_for_removal_summary,
    "missing_long_flagged": missing_long_flagged,
       
    
    #-------------------------------------------------
    # Counts
    #-------------------------------------------------
    "counts_subject": counts_subject,
    "counts_subject_grade": counts_subject_grade,
    "counts_by_district": counts_by_district,
    "counts_by_district_grade": counts_by_district_grade,
    
    # ------------------------------------------------
    # LONG MISSINGNESS
    # ------------------------------------------------
    "missing_long_by_file_only": missing_long_by_file_only,
    "missing_long_by_grade_and_file": missing_long_by_grade_and_file,
    

    # ------------------------------------------------
    # WIDE MISSINGNESS
    # ------------------------------------------------
    "missing_wide_by_file_only": missing_by_file_only,
    "missing_wide_by_grade_and_file": missing_by_grade_and_file,
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