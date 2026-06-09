# -*- coding: utf-8 -*-
"""
Created on Tue Jun  9 14:09:02 2026

@author: Chris.Wells
"""

import pandas as pd
import numpy as np
from typing import List, Optional

def missingness_long(
    df: pd.DataFrame,
    group_cols: List[str],
    treat_empty_string_as_missing: bool = True,
    columns_to_summarize: Optional[List[str]] = None,
) -> pd.DataFrame:

    df = df.copy()

    # Treat empty strings as missing
    if treat_empty_string_as_missing:
        obj_cols = df.select_dtypes(include=["object", "string"]).columns
        df[obj_cols] = df[obj_cols].replace(r"^\s*$", np.nan, regex=True)

    # Columns to summarize
    if columns_to_summarize is None:
        columns_to_summarize = [c for c in df.columns if c not in group_cols]
    else:
        columns_to_summarize = [c for c in columns_to_summarize if c not in group_cols]

    # Total rows per group
    totals = (
        df.groupby(group_cols, dropna=False)
          .size()
          .rename("total_count")
          .reset_index()
    )

    # Missing counts
    missing = (
        df.groupby(group_cols, dropna=False)[columns_to_summarize]
          .apply(lambda g: g.isna().sum())
          .stack()
          .rename("missing_count")
          .reset_index()
          .rename(columns={"level_" + str(len(group_cols)): "col_name"})
    )

    out = missing.merge(totals, on=group_cols, how="left")

    out["non_missing_count"] = out["total_count"] - out["missing_count"]
    out["missing_percentage"] = (
        (out["missing_count"] / out["total_count"]) * 100
    ).round(2)

    out = out[
        group_cols
        + [
            "col_name",
            "total_count",
            "missing_count",
            "non_missing_count",
            "missing_percentage",
        ]
    ]

    return out



missing_by_grade_and_file = missingness_long(
    df=df_wide,
    group_cols=["grade", "filenameFromDistrict"]
)



missing_by_file_only = missingness_long(
    df=df_wide,
    group_cols=["filenameFromDistrict"]
)



# Results:
# - missing_by_grade_and_file
# - missing_by_file_only