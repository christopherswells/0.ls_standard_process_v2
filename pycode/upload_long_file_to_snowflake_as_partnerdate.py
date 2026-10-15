# -*- coding: utf-8 -*-
"""
Created on Thu Jul 23 16:49:58 2026

@author: Chris.Wells
"""
#----------------------------------------------------------
# UPLOAD PARTNER DATA TO SNOWFLAKE AND MERGE TO MAP GROWTH
#----------------------------------------------------------

import re
import pandas as pd
from typing import List, Tuple
import sys
from pathlib import Path
from common.ls_map_count_functions import establish_snowflake_connector
from snowflake.connector.pandas_tools import write_pandas



#spyder seems to get screwy with the wd sometimes
ROOT = Path(__file__).resolve().parents[1]   # goes up from pycode → repo root
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
    
# from pycode.settings import COMBINED_FILE
from pycode.settings import *



#--------------------------------------------------------------   
# ADD LONG with Settings PARTNER DATA TO SNOWFLAKE TABLE
#---------------------------------------------------------------

# IMPORT DF_LONG IF NOT ALREADY LOADED
if "df_long" in globals() and isinstance(df_long, pd.DataFrame):
    pass
else:
    # df_long_with_settings = pd.read_parquet(Path(DATA_ROOT) / "df_long.parquet")
    df_long = pd.read_parquet(Path(DATA_ROOT) / "df_long.parquet") 
    
    
# ----------------------------------------
# FINAL NULL STANDARDIZATION
# ----------------------------------------

# Convert empty strings to missing
obj_cols = df_long.select_dtypes(include=['object', 'string']).columns

df_long[obj_cols] = (
    df_long[obj_cols]
    .replace(r'^\s*$', pd.NA, regex=True)
)

# Optional: convert placeholder strings
df_long[obj_cols] = (
    df_long[obj_cols]
    .replace({
        'NA': pd.NA,
        'N/A': pd.NA,
        'NULL': pd.NA,
        'null': pd.NA
    })
)

# Convert all pandas missing values to Python None
df_long = df_long.where(pd.notna(df_long), None)
    
    
CONN = establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
  
success, nchunks, nrows, _ = write_pandas(
    CONN,
    # df_long_with_settings,
    df_long,
    table_name= partner_table_name,
    quote_identifiers=True,
    overwrite=True, #if False appends data
    auto_create_table=True
)

CONN.commit()
CONN.close()



#-----------------------------------------------------   
# ADD combined_file DATA TO TEMP SNOWFLAKE TABLE
#-----------------------------------------------------

# # IMPORT DF_LONG IF NOT ALREADY LOADED
if "df_wide" in globals() and isinstance(df_wide, pd.DataFrame):
    pass
else:
    df_wide = pd.read_parquet(Path(DATA_ROOT) / "df_wide.parquet")
    
    
CONN = establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
  
success, nchunks, nrows, _ = write_pandas(
    CONN,
    df_wide,
    table_name= combined_file_table_name,
    quote_identifiers=True,
    overwrite=True, #if False appends data
    auto_create_table=True
)

CONN.commit()
CONN.close()



#-----------------------------------------------------   
# ADD SETTINGS TO SNOWFLAKE TABLE
#-----------------------------------------------------
# # IMPORT DF_LONG IF NOT ALREADY LOADED
# if "settings_prefixed" in globals() and isinstance(settings_prefixed, pd.DataFrame):
#     pass
# else:
#     settings_prefixed = pd.read_parquet(Path(DATA_ROOT) / "settings_prefixed.parquet")

    
# CONN = establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
  
# success, nchunks, nrows, _ = write_pandas(
#     CONN,
#     settings_prefixed,
#     table_name= settings_table_name,
#     quote_identifiers=True,
#     overwrite=True, #if False appends data
#     auto_create_table=True
# )

# CONN.commit()
# CONN.close()

