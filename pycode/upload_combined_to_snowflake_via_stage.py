# -*- coding: utf-8 -*-
"""
Created on Thu Jul 23 14:48:28 2026

@author: Chris.Wells


This code uploads thecombined file to snowflake to be the 
unedited partner data (other than nan/spaces... to pd.NA)

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
    
# from pycode.settings import COMBINED_FILE
from pycode.settings import *


# GET COMBINED FILE FROM GLOBALS IF EXISTS ELSE FROM COMBINED FILE IN EXCEL
if "combinedDf" in globals() and isinstance(combinedDf, pd.DataFrame):
    df_wide = combinedDf
else:
    df_wide = pd.read_excel(COMBINED_FILE, dtype=str, engine="openpyxl")
   

df = df_wide.copy()


#===============================================================
# UPLOAD TO STAGE
#===============================================================
success, nchunks, nrows, _ = write_pandas(
    CONN,
    df,
    table_name=combined_file_stage_table_name,
    overwrite=True,
    auto_create_table=True,
    quote_identifiers=True
)


#===============================================================
# CREATE PARTNER DATA FILE IF NOT EXISTS
#===============================================================
cursor.execute(f"""
CREATE TABLE IF NOT EXISTS {combined_file_table_name}
LIKE {combined_file_stage_table_name}
""")


# BUILD MERGE
merge_cols = [
    c for c in df.columns
    if c.upper() != 'FILENAMEFROMDISTRICT'
]


on_clause = "\nAND ".join(
    [
        f't."{col}" <=> s."{col}"'
        for col in merge_cols
    ]
)


insert_columns = ", ".join(
    [f'"{col}"' for col in df.columns]
)

insert_values = ", ".join(
    [f's."{col}"' for col in df.columns]
)


merge_sql = f"""
MERGE INTO {combined_file_table_name} t
USING {combined_file_stage_table_name} s
ON
{on_clause}

WHEN NOT MATCHED THEN
INSERT (
    {insert_columns}
)
VALUES (
    {insert_values}
)
"""


cursor.execute(merge_sql)

CONN.commit()