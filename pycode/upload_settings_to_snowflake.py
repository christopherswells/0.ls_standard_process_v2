# -*- coding: utf-8 -*-
"""
Upload the prepared settings dataset to Snowflake.

This script only loads settings_prefixed.parquet and writes it to the
Snowflake table configured by settings_table_name.
"""
from pathlib import Path
import pandas as pd
import sys
from common.ls_map_count_functions import establish_snowflake_connector
from snowflake.connector.pandas_tools import write_pandas

# Spyder sometimes gets screwy with the working directory
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pycode.settings import *  # expects WORKING_FILES, DATA_TEMPLATE, COMBINED_FILE


#--------------------------------------------------------------   
# import settings
#---------------------------------------------------------------

settings_path = SETTINGS_EXCEL_FILE

if not settings_path.exists():
    raise FileNotFoundError(
        f"Settings file was not found: {settings_path}"
    )

settings = pd.read_excel(settings_path)

if settings.empty:
    raise ValueError(
        "The settings file contains no records; upload was stopped."
    )




#--------------------------------------------------------------   
# MAKE HEADERS UPCASE AND PREFIX WITH 'SETTINGS_'
#---------------------------------------------------------------
settings.columns = ['SETTINGS_' + col.upper() for col in settings.columns]



# ----------------------------------------
# CLEAN & STANDARDIZE SETTINGS DF
# ----------------------------------------

# 1. Ensure SETTINGS_STUDY_GRADES is always a clean string
settings["SETTINGS_STUDY_GRADES"] = (
    settings["SETTINGS_STUDY_GRADES"]
    .astype("string")
    .str.strip()
)

# 2. Standardize null-like values
settings = settings.replace(
    [
        "",
        "NA", "N/A",
        "NULL", "null",
        "None", "none",
        "nan",
        "<NA>"
    ],
    pd.NA
)

# 3. Create SETTINGS_GRADE_LIST as a true list[int]
def parse_grade_list(val):
    if pd.isna(val):
        return None
    # split "3,4,5" → ["3","4","5"]
    parts = str(val).split(",")
    # convert to ints safely
    out = []
    for p in parts:
        p = p.strip()
        if p.isdigit():
            out.append(int(p))
    return out if out else None

settings["SETTINGS_GRADE_LIST"] = settings["SETTINGS_STUDY_GRADES"].apply(parse_grade_list)



#-----------------------------------------------------   
# ADD SETTINGS TO SNOWFLAKE TABLE
#-----------------------------------------------------
    
CONN = establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
  
success, nchunks, nrows, _ = write_pandas(
    CONN,
    settings,
    table_name= settings_table_name,
    quote_identifiers=True,
    overwrite=True, #if False appends data
    auto_create_table=True
)

CONN.commit()
CONN.close()