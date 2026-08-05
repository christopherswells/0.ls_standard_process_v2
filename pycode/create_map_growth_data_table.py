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

# IN SPYDER THE WORKING DIR IS NOT ALWAYS SETTING TO THE PROJECT DIR.  HARDCODED THE PROJECT DIR LOCATION.
os.chdir(r'K:\SMS Team\Chris_Wells\3.Linking\0. Standard Process\Linking_Studies_Data_Prep_code')
sys.path.append(r'K:\SMS Team\Chris_Wells\3.Linking\0. Standard Process\Linking_Studies_Data_Prep_code')

# CHECK IF THE CWD --> ...\Linking_Studies_Data_Prep_code
if os.path.basename(os.getcwd())  != 'Linking_Studies_Data_Prep_code':
    print('Your Working directory is : ' + os.getcwd())
    print('Your Working directory should be the location of this folder: "Linking_Studies_Data_Prep_code"')
    

from common.LS_MAP_Count_Functions import establish_snowflake_connector
# from common.LS_MAP_Count_Functions import run_map_counts_query
from common.LS_MAP_Count_Functions import output_to_excel_tab
from common.LS_MAP_Count_Functions import add_variables_to_sql_template
from common.LS_MAP_Count_Functions import query_snowflake
from py.settings import *


#------------------------------------------------------------------
# run: query_create_map_growth_table
#------------------------------------------------------------------

# CODE NO LONGER DISTINGUISHING BETWEEN EOG AND EOC/HS TESTS
ALL_TEST_NAMES = ", ".join(f"'{TEST}'" for TEST in MAP_TEST_NAMES)

# SET VARIABLES AND SQL QUERY
variables = {
        'MAP_TABLE_NAME': map_table_name ,
        'DATA_YEAR'     : DATA_YEAR ,
        'STATE_ABR'     : STATE_ABR ,
        # 'STATE_NAME'  : STATE_NAME,  
        'TERM_NUMBER'   : TERM_NUMBER,
        'TESTNAMES'     : ALL_TEST_NAMES
    }
SQLSCRIPT = os.path.join(SQL_PATH, "get_map_data_by_testname_from_tables_v2.sql")

# SUBSTITUTE VARS INTO QUERY
query_create_map_growth_table = add_variables_to_sql_template( SQLSCRIPT, variables)

# RUN QUERY
# merged_data = query_snowflake(query_create_studysample_qa, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
query_snowflake(query_create_map_growth_table, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)



