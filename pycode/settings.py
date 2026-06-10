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
# TERM_NUMBER = '202502'      # TERM OF DATA
# STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
# STATE_NAME = 'ILLINOIS' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
# STATE_ABR = 'IL'
# DATA_YEAR = TERM_NUMBER[:4] 

# ------ OK2026 ---------
# TERM_NUMBER = '202502'      # TERM OF DATA
# STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
# STATE_NAME = 'OKLAHOMA' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
# STATE_ABR = 'OK'
# DATA_YEAR = TERM_NUMBER[:4] 

# ------ PA2026 ---------
TERM_NUMBER = '202502'      # TERM OF DATA
STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
STATE_NAME = 'PENNSYLVANIA' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
STATE_ABR = 'PA'
DATA_YEAR = TERM_NUMBER[:4] 


# ------ WI2025 ---------
# TERM_NUMBER = '202502'      # TERM OF DATA
# STUDY_YEAR = '2026'         # YEAR STUDY IS CONDUCTED--used in data and project path
# STATE_NAME = 'WISCONSIN' 	# FOR QUERY.  ALL CAPS WITH '_' SEPARATING WORDS.
# STATE_ABR = 'WI'
# DATA_YEAR = TERM_NUMBER[:4] 

#===============================================================
# INPUT/OUTPUT LOCATIONS
# ==============================================================

SDRIVE = r'S:\MAPGrowth\Linking\Data Files\\'


# STANDARD LOCATION IN S:\\{STUDY_YEAR}\{ST}
DATA_ROOT = os.path.join(SDRIVE, STUDY_YEAR, STATE_ABR)


# IF NON-STANDARD DATA LOCATION
# DATA_ROOT = r'S:\MAPGrowth\Linking\Data Files\2026\IL_v2'


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


#===============================================================
# SETTINGS-- GLOBAL VARIABLES TO RUN STUDY SCRIPTS
#===============================================================

try:
    settings_xl = pd.read_excel(SETTINGS_EXCEL_FILE)
    # settings_xl = pd.read_excel(SETTINGS_EXCEL_FILE, sheet_name = settings)
    # settings_xl['STUDY_GRADES'] = settings_xl['STUDY_GRADES'].fillna(DEFAULT_GRADES)
    # settings_xl['STUDY_GRADES'] = settings_xl['STUDY_GRADES'].apply(lambda x: [int(g) for g in str(x).split(',')])
    
except:
    print()
    print('DOES THE SETTINGS.PY FILE IN THE ROOT HAVE A SETTINGS TAB?')
    print(DATA_ROOT)
    


#=====================================================
# SUBJECT NUMBERS FOR MAP GROWTH TESTS
#=====================================================
# SUBJECTS = [1, 2, 4, 100, 101, 102, 108]  #SC 2025
# MAP_SUBJECT_CODES = [1,2,4] #IL
MAP_SUBJECT_CODES = [1,2]

# HOW TO HANDLE CHANGES?
SUFFIXES = ["SS", "PLCODE", "PLDESC", "TESTNAME", "TESTDATE", "RETEST"]


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
