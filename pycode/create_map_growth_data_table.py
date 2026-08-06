# -*- coding: utf-8 -*-
"""
Created on Thu Aug 21 07:49:08 2025

@author: Chris.Wells

Create MAP Growth table in Snowflake

title :  $STATE_ABR$DATA_YEAR_MAPDATA 


running this from get_map_data_by_testnames_from_tables_v2.sql
which uses 5 phases of merge.


"""
import pandas as pd
import sys
from pathlib import Path



#----------------------------------------------------------------------
# SET WORKING DIRECTORY TO LOCATION OF 'Linking_Studies_Data_Prep_Code
#----------------------------------------------------------------------

import os

# Spyder sometimes gets screwy with the working directory
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

   

from common.ls_map_count_functions import establish_snowflake_connector
# from common.LS_MAP_Count_Functions import run_map_counts_query
from common.ls_map_count_functions import output_to_excel_tab
from common.ls_map_count_functions import add_variables_to_sql_template
from common.ls_map_count_functions import query_snowflake
from common.ls_map_count_functions import query_snowflake_sqlalchemy
from pycode.settings import *



#------------------------------------------------------------------
# run: query_create_map_growth_table
#------------------------------------------------------------------

SQL_PATH = ROOT / "common" / "py_sql"
print(SQL_PATH)

# CODE NO LONGER DISTINGUISHING BETWEEN EOG AND EOC/HS TESTS
ALL_TEST_NAMES = ", ".join(f"'{TEST}'" for TEST in map_test_names)

# SET VARIABLES AND SQL QUERY
variables = {
        'MAP_TABLE_NAME': f'LINKING_STUDIES.{map_table_name}' ,
        'DATA_YEAR'     : DATA_YEAR ,
        'STATE_ABR'     : STATE_ABR ,
        # 'STATE_NAME'  : STATE_NAME,  
        'TERM_NUMBER'   : TERM_NUMBER,
        'TESTNAMES'     : ALL_TEST_NAMES
    }
SQLSCRIPT = os.path.join(SQL_PATH, "get_map_data_by_testnames_from_tables_v2.sql")

# SUBSTITUTE VARS INTO QUERY
query_create_map_growth_table = add_variables_to_sql_template( SQLSCRIPT, variables)

# RUN QUERY
# merged_data = query_snowflake(query_create_studysample_qa, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
# query_snowflake(query_create_map_growth_table, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)

#switch to sql alchemy 
query_snowflake_sqlalchemy(query_create_map_growth_table, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)



