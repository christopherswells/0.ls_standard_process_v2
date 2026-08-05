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

from common.ls_map_count_functions import output_to_excel_tab
from common.ls_map_count_functions import add_timestamp_to_path


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

#-------------IL2025------
# TERM_NUMBER = '202502'      # TERM OF DATA
# STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
# STATE_NAME = 'ILLINOIS' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
# STATE_ABR = 'IL'
# DATA_YEAR = TERM_NUMBER[:4] 
# SUFFIXES = ["SS", "PLCODE", "PLDESC", "TESTNAME", "TESTDATE", "RETEST"]

# ------ OK2026 ---------
TERM_NUMBER = '202502'      # TERM OF DATA
STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
STATE_NAME = 'OKLAHOMA' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
STATE_ABR = 'OK'
DATA_YEAR = TERM_NUMBER[:4] 

SUFFIXES = ["SS", "PLCODE", "PLDESC", "TESTNAME", "TESTDATE"
            ,"SS_CONVERTED","SS_UNCONVERTED"]

# ------ PA2026 ---------
# TERM_NUMBER = '202502'      # TERM OF DATA
# STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
# STATE_NAME = 'PENNSYLVANIA' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
# STATE_ABR = 'PA'
# DATA_YEAR = TERM_NUMBER[:4] 
# SUFFIXES = ["SS", "PLCODE", "PLDESC", "TESTNAME", "TESTDATE", "RETEST"]

# map_subject_codes = [1, 2, 100]  # for initial MAP counts


# ------ WI2025 ---------
# TERM_NUMBER = '202502'      # TERM OF DATA
# STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
# STATE_NAME = 'WISCONSIN' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
# STATE_ABR = 'WI'
# DATA_YEAR = TERM_NUMBER[:4] 
# SUFFIXES = ["SS", "PLCODE", "PLDESC", "TESTNAME", "TESTDATE", "RETEST"]


# ------ TX2026 ---------
# TERM_NUMBER = '202602'      # TERM OF DATA
# STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
# STATE_NAME = 'TEXAS' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
# STATE_ABR = 'TX'
# DATA_YEAR = TERM_NUMBER[:4] 
# SUFFIXES = ["SS", "PLCODE", "PLDESC", "TESTNAME", "TESTDATE", "RETEST"]


#------ COLORADO-------
# TERM_NUMBER = '202602'      # TERM OF DATA
# STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
# STATE_NAME = 'COLORADO' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
# STATE_ABR = 'CO'
# DATA_YEAR = TERM_NUMBER[:4] 


#------ UTAH -------
# TERM_NUMBER = '202602'      # TERM OF DATA
# STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
# STATE_NAME = 'UTAH' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
# STATE_ABR = 'UT'
# DATA_YEAR = TERM_NUMBER[:4] 


#tx


#initialize
map_test_names = []


#===============================================================
# INPUT/OUTPUT LOCATIONS
#==============================================================

SDRIVE = r'S:\MAPGrowth\Linking\Data Files\\'


# STANDARD LOCATION IN S:\\{STUDY_YEAR}\{ST}
DATA_ROOT = os.path.join(SDRIVE, STUDY_YEAR, STATE_ABR)

# IF NON-STANDARD DATA LOCATION
# DATA_ROOT = r'S:\MAPGrowth\Linking\Data Files\2026\TX\spanish'    # for IL USING V2 CODE

# PARTNER DATA RAW TO SNOWFLAKE LINKING STUDIES SCHEMA
combined_file_table_name = ( f"{STATE_ABR}{STUDY_YEAR}_COMBINED_FILE").upper()
combined_file_stage_table_name = (f"{combined_file_table_name}_STAGE")



# PRINT THE DATA ROOT
print("DATA_ROOT =", DATA_ROOT)

#---------------------------------------------------------------
# FILE FOLDERS-- will be created if not exist
#---------------------------------------------------------------
DATA_ROOT = Path(DATA_ROOT)

ORIGINAL_FILES = DATA_ROOT / "original_files"
REJECTED_FILES = DATA_ROOT / "rejected_files"
EDITED_FILES = DATA_ROOT  / "edited_files"
WORKING_FILES = DATA_ROOT / "working_files"


for folder in [ORIGINAL_FILES, REJECTED_FILES, EDITED_FILES, WORKING_FILES]:
    folder.mkdir(parents=True, exist_ok=True)


#full output path + filename
OUTMAPCOUNTS = os.path.join(DATA_ROOT , STATE_ABR + DATA_YEAR +'_mapcounts.xlsx' )

#------------------------------------------------------------------
# OUTPUT-- 
# STOP PROGRAM IF FOLDER ALREADY EXISTS.  RENAME MANUALLY (eg V1)
# AND RESTART PROGRAM.  
# TODO: ADD AUTO-VERSIONING OR   
#------------------------------------------------------------------

def make_versioned_dir(base_path: Path) -> Path:
    """
    Create a versioned directory:
    base_path, base_path_1, base_path_2, ...
    Returns the path that was created.
    """
    if not base_path.exists():
        base_path.mkdir(parents=True)
        print(f"[INFO] Created: {base_path}")
        return base_path

    # If base exists, increment
    counter = 1
    while True:
        candidate = Path(f"{base_path}_{counter}")
        if not candidate.exists():
            candidate.mkdir(parents=True)
            print(f"[INFO] Created: {candidate}")
            return candidate
        counter += 1


OUTPUT = DATA_ROOT / "output"
# OUTPUT = make_versioned_dir(OUTPUT)


# if OUTPUT.exists():
#     print(f"[ERROR] Output path already exists: {OUTPUT}")
#     sys.exit(1)

# else:
#     OUTPUT.mkdir(parents=True, exist_ok=True)
    


#-------------------------------
# FILES
#-------------------------------

#INPUT FILES
DATA_TEMPLATE = DATA_ROOT / f"{STATE_ABR}{DATA_YEAR}_data_template.xlsx"

SETTINGS_EXCEL_FILE = DATA_ROOT / f"{STATE_ABR}{DATA_YEAR}_data_prep_settings.xlsx"



#OUTPUT FILES
OUT_MAP_COUNTS = DATA_ROOT / f"{STATE_ABR}{DATA_YEAR}_map_counts.xlsx"

OUT_PARTNER_COUNTS = DATA_ROOT / f"{STATE_ABR}{DATA_YEAR}_partner_counts.xlsx"

#adds timestamp to partner counts
OUT_PARTNER_COUNTS_TS = add_timestamp_to_path(OUT_PARTNER_COUNTS)

DATA_LOG = DATA_ROOT / f"{STATE_ABR}{DATA_YEAR}_district_data_log.xlsx"

COMBINED_FILE = DATA_ROOT / f"{STATE_ABR}{DATA_YEAR}_combined_file.xlsx"


#TABLES -- SHOULD THESE BE STUDY OR DATA YEAR?
partner_table_name = ( f"{STATE_ABR}{DATA_YEAR}_PARTNERDATA").upper()

combined_file_table_name = ( f"{STATE_ABR}{DATA_YEAR}_COMBINED_FILE").upper()

settings_table_name = ( f"{STATE_ABR}{DATA_YEAR}_STUDY_SETTINGS").upper()



#===============================================================
# SETTINGS-- GLOBAL VARIABLES TO RUN STUDY SCRIPTS
#===============================================================

settings_xl = None

try:
    settings_xl = pd.read_excel(SETTINGS_EXCEL_FILE)
   
except:
    print()
    print('Is there a settings file here with settings tab?:')
    print(DATA_ROOT)
    


#===============================================================
# BUILD TESTNAME → GRADE LIST MAPPING
#===============================================================


if settings_xl is not None and not settings_xl.empty:
    df = settings_xl.copy()
    df.columns = df.columns.str.strip()

    if 'D_MAPGROWTH_TEST_NAME' in df.columns and 'STUDY_GRADES' in df.columns:
        # Normalize grades into list[int]
        def parse_grades(x):
            if pd.isna(x):
                return []
            return [int(g.strip()) for g in str(x).split(',') if g.strip()]

        df['STUDY_GRADES_LIST'] = df['STUDY_GRADES'].apply(parse_grades)

        # explode → group → collect unique grades per test
        exploded = df[['D_MAPGROWTH_TEST_NAME', 'STUDY_GRADES_LIST']].explode('STUDY_GRADES_LIST')

        map_test_grades = (
            exploded
            .dropna(subset=['STUDY_GRADES_LIST'])
            .groupby('D_MAPGROWTH_TEST_NAME')['STUDY_GRADES_LIST']
            .apply(lambda x: sorted(set(int(v) for v in x)))
            .to_dict()
        )
        
        #map tests in study        
        map_test_names  =  [k.strip() for k in map_test_grades.keys()]
        
        

#========================================================
# SUBJECT NUMBERS FOR MAP Counts if settings.py not exist
# sometimes initial map counts prior to knowing
# all exact testnames and/or grades, etc.  can use
# just subject codes to explore.
#========================================================
# SUBJECTS = [1, 2, 4, 100, 101, 102, 108]  #SC 2025
# MAP_SUBJECT_CODES = [1,2,4] #IL

   

# HOW TO HANDLE CHANGES?-- putting up top for OK2025
# SUFFIXES = ["SS", "PLCODE", "PLDESC", "TESTNAME", "TESTDATE", "RETEST"]


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
# MAP_TEST_NAMES = [
#             'Growth: Math 2-5 CCSS 2010 1.1'
#             ,'Growth: Math 6+ CCSS 2010 1.1'
#             ,'Growth: Reading 2-5 CCSS 2010 1.1'
#             ,'Growth: Reading 6+ CCSS 2010 1.1'
#             ,'Growth: Science 2-5: for use with NGSS 2013 1.1'
#             ,'Growth: Science 6-8: for use with NGSS 2013 1.1'  
#     ]



#-------------------------------------------------------------
# EOC Grade Range:
# •     EOC Algebra 1 to MAP Growth Math6+, grades 6-10
# •     EOC Algebra 1 to MAP Growth Algebra 1, any applicable grades
# •     EOC Algebra 2 should not be linked to MAP Growth Math6+, as they are not aligned
# •     EOC Algebra 2 to MAP Growth Algebra 2, any applicable grades
# •     EOC Geometry should not be linked to MAP Growth Math6+, as they are not aligned
# •     EOC English 1 to MAP Growth Reading6+, grades 7-10
# •     EOC English 2 to MAP Growth Reading6+, grades 8-10
# •     EOC Biology to MAP Growth Science 9-12, grades 9-10
# o     Grades 11-12 are not included because the general science student achievement norms are for grades 2-10
# •     EOC Biology to MAP Growth Science 9-12 Life Science/Biology, any applicable grades
#-------------------------------------------------------------
