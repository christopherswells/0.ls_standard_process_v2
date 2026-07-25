# -*- coding: utf-8 -*-
"""
Created on Thu Jul 23 16:49:58 2026

@author: Chris.Wells
"""
#----------------------------------------------------------
# UPLOAD SETTINGS_XL TO SNOWFLAKE
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
# make study_grades a list
#-----------------------------------------------------

def parse_study_grades(raw: str) -> list[int]:
    if raw is None or pd.isna(raw):
        return []

    s = str(raw).upper().strip()

    # split on commas, spaces, semicolons
    tokens = re.split(r"[,\s;]+", s)

    out = []

    for t in tokens:
        if not t:
            continue

        # handle ranges like "3-5"
        if "-" in t:
            a, b = t.split("-", 1)
            a = a.strip()
            b = b.strip()
            if a in reverse_map and b in reverse_map:
                lo = reverse_map[a]
                hi = reverse_map[b]
                out.extend(range(lo, hi + 1))
            continue

        # direct lookup
        if t in reverse_map:
            out.append(reverse_map[t])

    return sorted(set(out))



#-----------------------------------------------------   
# ADD SETTINGS TO SNOWFLAKE TABLE
#-----------------------------------------------------
# settings_xl["STUDY_GRADES"] = settings_xl["STUDY_GRADES"].apply(
#     lambda x: None if pd.isna(x) else str(x)
# )
    
# CONN = establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
  
# success, nchunks, nrows, _ = write_pandas(
#     CONN,
#     settings_xl,
#     table_name= SETTINGS_EXCEL_FILE,
#     quote_identifiers=True,
#     overwrite=True, #if False appends data
#     auto_create_table=True
# )

# CONN.commit()
# CONN.close()

