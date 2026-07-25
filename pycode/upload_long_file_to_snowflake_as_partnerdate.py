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





#-----------------------------------------------------   
# ADD PARTNER DATA TO TEMP SNOWFLAKE TABLE
#-----------------------------------------------------

# IMPORT DF_LONG IF NOT ALREADY LOADED
if "df_long" in globals() and isinstance(df_long, pd.DataFrame):
    pass
else:
    df_long = pd.read_parquet(Path(DATA_ROOT) / "df_long.parquet")
    
    
CONN = establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
  
success, nchunks, nrows, _ = write_pandas(
    CONN,
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
    
    
# CONN = establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
  
# success, nchunks, nrows, _ = write_pandas(
#     CONN,
#     df_wide,
#     table_name= combined_file_table_name,
#     quote_identifiers=True,
#     overwrite=True, #if False appends data
#     auto_create_table=True
# )

# CONN.commit()
# CONN.close()
