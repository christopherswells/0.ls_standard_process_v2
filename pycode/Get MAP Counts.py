#==============================================================================
# GET MAP Partner Counts.py
#
# queries Snowflake databvase for counts of MAP test events for a given
# linking study.
#
# This code keys off of specific testnames.  the first query
# Total_Counts_All_Tests.sql gives all test counts in provided subject codes
# Determine which testnames have sufficient counts to run the remaing queries.
#
# your Working directory should be set to '...\Linking_Studies_Data_Prep_code'
#
#
# TODO: change to have total testconts per subject counted first
#        then run remaing code on testnames.
# TODO: run by cell and/or put in jupyter notebook
#==============================================================================

import pandas as pd
import sys
from pathlib import Path



#----------------------------------------------------------------------
# SET WORKING DIRECTORY TO LOCATION OF 'Linking_Studies_Data_Prep_Code
#----------------------------------------------------------------------

import os

# IN SPYDER THE WORKING DIR IS NOT ALWAYS SETTING TO THE PROJECT DIR.  HARDCODED THE PROJECT DIR LOCATION.
# os.chdir(r'K:\SMS Team\Chris_Wells\3.Linking\0. Standard Process\Linking_Studies_Data_Prep_code')
# sys.path.append(r'K:\SMS Team\Chris_Wells\3.Linking\0. Standard Process\Linking_Studies_Data_Prep_code')

# CHECK IF THE CWD --> ...\Linking_Studies_Data_Prep_code
# if os.path.basename(os.getcwd())  != 'Linking_Studies_Data_Prep_code':
#     print('Your Working directory is : ' + os.getcwd())
#     print('Your Working directory should be the location of this folder: "Linking_Studies_Data_Prep_code"')
    

# from common.ls_map_count_functions import establish_snowflake_connector
# from common.ls_map_count_functions import run_map_counts_query
from common.ls_map_count_functions import output_to_excel_tab
from common.ls_map_count_functions import add_variables_to_sql_template
from common.ls_map_count_functions import query_snowflake
from common.ls_map_count_functions import query_snowflake_sqlalchemy
from pycode.settings import *



# #===============================================================
# # SETTINGS -- typically more permanent parameters than the
# # project settings in ...\py\settings.py
# #===============================================================


# SQL SCRIPTS- found in ...\Linking_Studies_Data_Prep_code\sql folder
# called py_sql because it is coded to run in Python. minor editing will be 
# needed to run in sql.
SQL_PATH = os.path.join(os.getcwd(), 'common','py_sql' )
print(SQL_PATH)



#------------------------------------------------------------------
# run: Total_Counts_All_Tests.sql
# TO GET EXACT TESTNAMES TO KEY REMAINING COUNT QUERIES
#------------------------------------------------------------------
SUBJECT_STR = '(' + ', '.join(map(str, map_subject_codes)) + ')'

# ADD SETTINGS
variables = {
        'TERM_NUMBER': TERM_NUMBER ,
        'STATE_NAME': STATE_NAME ,
        'SUBJECT_STR': SUBJECT_STR
        # ,    
        # 'TESTNAMES': EOG_TEST_NAMES
    }


SQLSCRIPT = os.path.join(SQL_PATH, "Total_Counts_All_Tests.sql")
# Total_Counts_All_Tests, query_Total_Counts_All_Tests = run_map_counts_query( SQLSCRIPT , variables, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
query_Total_Counts_All_Tests = add_variables_to_sql_template( SQLSCRIPT, variables)
Total_Counts_All_Tests = query_snowflake_sqlalchemy(query_Total_Counts_All_Tests, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)




#===============================================================
# ADDITIONAL SETTINGS AND SETTINGS PREP
# to get counts by testname
#===============================================================
MAP_TESTS_TO_COUNT =  ", ".join(f"'{TEST}'" for TEST in map_test_names)


#==================================================================
# GET COUNTS BY TESTNAME -- (TESTNAMES DETERMINED FROM QUERY ABOVE)
#==================================================================

if MAP_TESTS_TO_COUNT:
    variables = {
            'TERM_NUMBER': TERM_NUMBER ,
            'STATE_NAME': STATE_NAME ,            
            # 'MIN_GRADE':'3',
            # 'MAX_GRADE':'8' ,
            'TESTNAMES': MAP_TESTS_TO_COUNT
        }
    
    #------------------------------------------------------------------
    # run: Counts_By_Grade.sql
    #------------------------------------------------------------------    
    SQLSCRIPT = os.path.join(SQL_PATH,  "Counts_By_Grade.sql")
    query_Counts_By_Grade = add_variables_to_sql_template( SQLSCRIPT, variables)
    # Counts_By_Grade = query_snowflake(query_Counts_By_Grade, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
    Counts_By_Grade = query_snowflake_sqlalchemy(query_Counts_By_Grade, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)

    #------------------------------------------------------------------
    # run: Counts_By_District.sql
    #------------------------------------------------------------------    
    SQLSCRIPT = os.path.join(SQL_PATH,  "Counts_By_District.sql")
    query_Counts_By_District = add_variables_to_sql_template( SQLSCRIPT, variables)
    Counts_By_District = query_snowflake_sqlalchemy(query_Counts_By_District, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)

    #------------------------------------------------------------------
    # run: Counts_By_District_Grade.sql
    #------------------------------------------------------------------    
    SQLSCRIPT = os.path.join(SQL_PATH,  "Counts_By_District_Grade.sql")
    query_Counts_By_District_Grade = add_variables_to_sql_template( SQLSCRIPT, variables)
    Counts_By_District_Grade = query_snowflake_sqlalchemy(query_Counts_By_District_Grade, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)

    
else:
    print('no specific test names.')


#================================================================
# OUTPUT
#================================================================
# List of (sheet_name, variable_name) pairs
sheet_vars = [
    ('Total_Counts_All_Tests', 'Total_Counts_All_Tests'),
    ('Counts_By_Grade', 'Counts_By_Grade'),    
    ('Counts_By_District', 'Counts_By_District'),
    ('Counts_By_District_Grade', 'Counts_By_District_Grade')
]

# Build the dictionary only with existing DataFrames
outputDict = {
    sheet: globals()[var]
    for sheet, var in sheet_vars
    if var in globals() and isinstance(globals()[var], pd.DataFrame)
}


output_to_excel_tab(outputDict, OUTMAPCOUNTS)




