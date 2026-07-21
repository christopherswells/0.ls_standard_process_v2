# -*- coding: utf-8 -*-
"""
Created on Tue Jun  9 20:35:24 2026

@author: Chris.Wells
"""


import pandas as pd
import numpy as np
from typing import List, Optional
from pycode.settings import *

#deciding what reports to keep.  will move helper functionslayter

from common.ls_map_count_functions import missingness_long 



#-----------------------------------------------------
# re-import data 
#-----------------------------------------------------
df_long = pd.read_parquet(DATA_ROOT / "df_long.parquet")

df_wide = pd.read_parquet(DATA_ROOT / "df_wide.parquet")




#----------------------------------------------------
# MISSING WIDE
#----------------------------------------------------
missing_by_grade_and_file = missingness_long(
    df=df_wide,
    group_cols=["grade", "filenameFromDistrict"]
)



missing_by_file_only = missingness_long(
    df=df_wide,
    group_cols=["filenameFromDistrict"]
)






#----------------------------------------------------
# MISSINGNESS of df_long
#----------------------------------------------------
# --- Missingness for df_long ---

missing_long_by_grade_and_file = missingness_long(
    df=df_long,
    group_cols=["grade", "filenameFromDistrict"]
)

missing_long_by_file_only = missingness_long(
    df=df_long,
    group_cols=["filenameFromDistrict"]
)



#----------------------------------------------------
# COUNTS SUBJECT
#----------------------------------------------------
counts_subject = (
    df_long
    .groupby(["SUBJECT"], dropna=False)
    .size()
    .rename("record_count")
    .reset_index()
    .sort_values([ "SUBJECT"])
)




#----------------------------------------------------
# COUNTS SUBJECT/GRADE
#----------------------------------------------------
counts_subject_grade = (
    df_long
    .groupby(["SUBJECT", "grade"], dropna=False)
    .size()
    .rename("record_count")
    .reset_index()
    .sort_values(["grade", "SUBJECT"])
)



#----------------------------------------------------
# OUTPUT COUNTS AND QA
#----------------------------------------------------

# --MOVE FILENAMEFORMDISTRICT TO LAST COLUMN FOR EASIER READING
# -- if filenamefromdistrict is in the respective summary
def move_col_to_end(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col not in df.columns:
        return df  # leave unchanged
    cols = [c for c in df.columns if c != col] + [col]
    return df[cols]


summaries = {
    "missing_wide_by_file_only": missing_by_file_only,
    "missing_wide_by_grade_and_file": missing_by_grade_and_file,
    "missing_long_by_file_only": missing_long_by_file_only,
    "missing_long_by_grade_and_file": missing_long_by_grade_and_file,
    "counts_subject": counts_subject,
    "counts_subject_grade": counts_subject_grade,
}

summaries = {
    name: move_col_to_end(df, "filenameFromDistrict")
    for name, df in summaries.items()
}


#---------------------------------
# OUTPUT
#---------------------------------

# output--timestamped output defined in settings.py
output_to_excel_tab(
    outputDict=summaries,
    outpath=str(OUT_PARTNER_COUNTS_TS)
)
