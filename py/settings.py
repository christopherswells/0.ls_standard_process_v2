# -*- coding: utf-8 -*-
"""
Created on Wed Aug 27 11:42:56 2025

@author: Chris.Wells


todo: WILL NEED TO CHANGE DEFAULT GRADES TO MATCH SUBJECT
      AND ADD STUDY_GRADES TO EXCEL SETTINGS

"""

import os
import pandas as pd
import sys

from pathlib import Path  #TODO: SWITCH PATHS TO THIS


#=====================================================
# SNOWFLAKE CONNECTION SETTINGS
#=====================================================
SNOWFLAKEUSER = 'christopher.wells@hmhco.com'

# LINKING STUDIES SCHEMA
ROLE = 'RESEARCH_PRD_MAPGROWTH_PSYCHOMETRIC_SOLUTIONS_FR'
WAREHOUSE = 'RESEARCH_PRD_MAPGROWTH_PSYCHOMETRIC_SOLUTIONS_WH'
DATABASE = 'RESEARCH_PRD_GRD_DB'
SCHEMA = 'LINKING_STUDIES'



#================================================================
#  STUDY SETTINGS FROM PLANNING FORM IN SHAREPOIONT
#================================================================
TERM_NUMBER = '202502'      # TERM OF DATA
STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
STATE_NAME = 'ILLINOIS' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
STATE_ABR = 'IL'
DATA_YEAR = TERM_NUMBER[:4] 


#===============================================================
# INPUT/OUTPUT LOCATIONS
# ==============================================================

SDRIVE = r'S:\MAPGrowth\Linking\Data Files\\'


# STANDARD LOCATION IN S:\\{STUDY_YEAR}\{ST}
# DATA_ROOT = os.path.join(SDRIVE, STUDY_YEAR, STATE_ABR)


# IF NON-STANDARD DATA LOCATION
DATA_ROOT = r'S:\MAPGrowth\Linking\Data Files\2026\IL_v2'


#---------------------------------------------------------------
# FILE FOLDERS-- will be created if not exist
#---------------------------------------------------------------
DATA_ROOT = Path(DATA_ROOT)

ORIGINAL_FILES = DATA_ROOT / "original_files"
REJECTED_FILES = DATA_ROOT / "rejected_files"
EDITED_FILES = DATA_ROOT / "edited_files"
WORKING_FILES = DATA_ROOT / "working_files"


for folder in [ORIGINAL_FILES, REJECTED_FILES, EDITED_FILES, WORKING_FILES]:
    folder.mkdir(parents=True, exist_ok=True)



#------------------------------------------------------------------
# OUTPUT-- 
# STOP PROGRAM IF FOLDER ALREADY EXISTS.  RENAME MANUALLY (eg V1)
# AND RESTART PROGRAM.  
# TODO: ADD AUTO-VERSIONING OR   
#------------------------------------------------------------------
OUTPUT = DATA_ROOT / "output"

if OUTPUT.exists():
    print(f"[ERROR] Output path already exists: {OUTPUT}")
    sys.exit(1)

else:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    


#-------------------------------
# FILES
#-------------------------------

#INPUT FILES
DATA_TEMPLATE = DATA_ROOT / f"{STATE_ABR}{DATA_YEAR}_data_template.xlsx"

COMBINED_FILE = DATA_ROOT / f"_{STATE_ABR}{DATA_YEAR}_combined_file"



#OUTPUT FILES
OUT_MAP_COUNTS = DATA_ROOT / f"{STATE_ABR}{DATA_YEAR}_map_counts.xlsx"

OUT_PARTNER_COUNTS = DATA_ROOT / f"{STATE_ABR}{DATA_YEAR}_partner_counts.xlsx"


#===============================================================
# SETTINGS-- GLOBAL VARIABLES TO RUN STUDY SCRIPTS
#===============================================================

# try:
#     settings_xl = pd.read_excel(SETTINGS_EXCEL_FILE, sheet_name = SETTINGS_EXCEL_FILE)
#     settings_xl['STUDY_GRADES'] = settings_xl['STUDY_GRADES'].fillna(DEFAULT_GRADES)
#     settings_xl['STUDY_GRADES'] = settings_xl['STUDY_GRADES'].apply(lambda x: [int(g) for g in str(x).split(',')])
    
# except:
#     print('DOES THE SETTINGS.PY FILE IN THE ROOT HAVE A SETTINGS TAB?')
#     print(DATA_ROOT)
    


#=====================================================
# SUBJECT NUMBERS FOR MAP GROWTH TESTS
#=====================================================
# SUBJECTS = [1, 2, 4, 100, 101, 102, 108]  #SC 2025
MAP_SUBJECT_CODES = [1,2,4]

'''
NWEA’s numeric subject code:
1: Math
2: Reading
3: Language Usage
4: Science - General Science
5: Science - Concepts and Processes
6: Social Studies
7: Reading - Spanish  (Note: Spanish Reading is coded 12 in Snowflake)
100: Algebra 1
101: Algebra 2
102: Geometry
103: Integrated Math 1
104: Integrated Math 1 and 2
105: Integrated Math 2
106: Integrated Math 3
107: Earth and Space Sciences
108: Life Sciences
109: Physical Sciences
110: Earth, Space, and Life Sciences
'''



#=====================================================
# MAP_TEST_NAMES-- FROM PLANNING FORM sect.1
# Content areas and grades to include in study 
# also alignmnet, section 3 for full test names.
#=====================================================
MAP_TEST_NAMES = [
            'Growth: Math 2-5 CCSS 2010 1.1'
            ,'Growth: Math 6+ CCSS 2010 1.1'
            ,'Growth: Reading 2-5 CCSS 2010 1.1'
            ,'Growth: Reading 6+ CCSS 2010 1.1'
            ,'Growth: Science 2-5: for use with NGSS 2013 1.1'
            ,'Growth: Science 6-8: for use with NGSS 2013 1.1'  
    ]








# TODO: ADJUST COMMON/PY_SQL QUERIES TO KEY OFF SETTINGS.XLSX - GRADES AND TESTNAMES
# TODO: TRY SETTINGS.XSLX ALONG WITH WORKSHETTS IN COMMON/GIT


#===============================================================
# SETTINGS excel in root (data files)
# change code to use this instead of settings on this page
# new 11/18/2025 for GA2024 and going forward.
# add race_pl_gender worksheets here
#===============================================================

# SETTINGS_EXCEL_FILE = os.path.join(DATA_ROOT, r'LS_data_prep_settings.xlsx')
# SETTINGS_EXCEL_FILE = os.path.join(DATA_ROOT, r'Settings.xlsx')
# settings_xl = pd.read_excel(SETTINGS_EXCEL_FILE, sheet_name = "settings")
# settings_xl['STUDY_GRADES'] = settings_xl['STUDY_GRADES'].apply(lambda x: [int(g) for g in str(x).split(',')])




#=============================================================
# STANDARD INPUT/OUTPOUT LOCATIONS
#=============================================================

#SQL codepath - used in create map table. could drop.
SQL_PATH = os.path.join(os.getcwd(), 'common','py_sql' )


#create output folder for partnerdata
datapath = os.path.join(DATA_ROOT, 'Working Files')

# Create output directory if not exists-- taken from scratch_dev_code.py
outPath = os.path.join(datapath ,'Output')
if not os.path.exists(outPath):
  
    os.makedirs(outPath)
    print("The Output directory was created: " + str(outPath))



#-------------------------------------------------------------
# •	Default EOC terms should be:
# o	EOC Algebra 1 to MAP Growth Math6+, grades 6-10
# o	EOC Algebra 1 to MAP Growth Algebra 1, any applicable grades
# o	EOC Algebra 2 should not be linked to MAP Growth Math6+, as they are not aligned
# o	EOC Algebra 2 to MAP Growth Algebra 2, any applicable grades
# o	EOC Geometry should not be linked to MAP Growth Math6+, as they are not aligned
# o	EOC English 1 to MAP Growth Reading6+, grades 7-10
# o	EOC English 2 to MAP Growth Reading6+, grades 8-10
# o	EOC Biology to MAP Growth Science 9-12, grades 9-10
# o	Grades 11-12 are not included because the general science student achievement norms are for grades 2-10
# o	EOC Biology to MAP Growth Science 9-12 Life Science/Biology, any applicable grades
#-------------------------------------------------------------
#TODO: this changed recently. for EOC see grade defaults by subject.
DEFAULT_GRADES = '6,7,8,9,10,11,12' # IF GRADES LEFT EMPTY IN SETTINGS.



#===================================================
# GET SETTINGS.  set grade DEFAULT_GRADES IF empty.
#===================================================
  
    
    
#=============================================================
# RELIC SETTINGS 
#=============================================================
# RELIC FROM OLD SETTINGS NOT YET REMOVED:
#-- THIS NEEDS TO BE IN FORM EG. 'ELA_SS' FOR NOW NOT 'ELA' AS IN SETTINGS.  
# UNTIL CODE IN THIS SCRIPT CHANGEED TO HANDLE GRADEGRANGE SETTINGS.
gradeRange = {          
                'ELA_SS'    : [3,4,5,6,7,8] ,
                'Math_SS'    : [3,4,5,6,7,8] ,
                'Science_SS'    : [5,8]                
                
              }   

SUBJECT_TO_MAP_TEST_MAPPING = {
    'ELA': ['Growth: Reading 2-5 CCSS 2010 1.1'
            ,'Growth: Reading 6+ CCSS 2010 1.1'],
    'Math': ['Growth: Math 2-5 CCSS 2010 1.1'
            ,'Growth: Math 6+ CCSS 2010 1.1'],
    'Science': ['Growth: Science 2-5: for use with NGSS 2013 1.1'
            ,'Growth: Science 6-8: for use with NGSS 2013 1.1']
    
    }


#---------------------------------------
# ADDING THIS FOR IL2025 TO GET IT DONE
#---------------------------------------
test_grade_map = {
    "Growth: Reading 2-5 CCSS 2010 1.1": [ 3, 4, 5],
    "Growth: Reading 6+ CCSS 2010 1.1": [6, 7, 8],
    "Growth: Math 2-5 CCSS 2010 1.1": [ 3, 4, 5],
    "Growth: Math 6+ CCSS 2010 1.1": [6, 7, 8],
    "Growth: Science 2-5: for use with NGSS 2013 1.1": [ 5],
    "Growth: Science 6-8: for use with NGSS 2013 1.1": [ 8],
}

# the subjects in gradeRAnge.
subjects = list(gradeRange.keys()) #USED FOR SUBJECT COUNTS IN CREATE_DISTRICT_COMINED...
SUBJECTNAMES = ['ELA','Math','Science']  #USED IN UPLOADE_COMBINED_FILE...

#FIELDS ASSOCIATED WITH SCORES--NEEDED FOR PIVOT
#TODO: USE STANDARD TEST NAMES AND CHECKE FOR, EX. 'ALGEBRA1_' as scorefield
SCORE_FIELD_SUBSCRIPTS = ['TESTNAME','SS','PLDESC','PLCODE','TESTDATE','RETEST']


# OUTPUT INFORMATION FOR PARTNER TABLE    
# PARTNER DATA TABLE NAME IN SNOWFLAKE- eg. GA2025_STUDY_PARTNERDATA_
partner_table_name = STATE_ABR + DATA_YEAR + '_LINKINGSTUDY_PARTNERDATA' 

#True if output the partner combined file to snwoflake partner data table
output_partnerdata_to_snowflake =  True   

#SUBJECT CODE MAP-- temp til settings xl complete
SUBJECT_CODE_MAP  = {
    'ELA': 2,
    'Math':1,
    'Science':4
    }


    
