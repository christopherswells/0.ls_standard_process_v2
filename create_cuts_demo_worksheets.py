# -*- coding: utf-8 -*-
"""
Created on Thu Oct  1 14:02:27 2026

@author: Chris.Wells

upload cuts/demo file

"""

from pathlib import Path
import re
import pandas as pd
from typing import Optional
import sys
import os

# Spyder sometimes gets screwy with the working directory
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pycode.settings import *  # expects WORKING_FILES, DATA_TEMPLATE, COMBINED_FILE
from common.ls_map_count_functions import *


#------------------------------------------------------------------------------
#  ADDITIONAL SETTINGS
#------------------------------------------------------------------------------

STUDY_TYPE = 'EOG'



#--------------------------------------------------------
# TODO: get corrected settings names earlier in process
# UPLOAD EDITED SETTINGS-- REPLACE CUTS_SUBJECT
#--------------------------------------------------------
# # IMPORT DF_LONG IF NOT ALREADY LOADED
    
CONN = establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
  
success, nchunks, nrows, _ = write_pandas(
    CONN,
    settings_xl,
    table_name= settings_table_name,
    quote_identifiers=True,
    overwrite=True, #if False appends data
    auto_create_table=True
)

CONN.commit()
CONN.close()




#------------------------------------------------------------------------------
#  STANDARD PATHS AND FILES
#------------------------------------------------------------------------------

# STANDARD LOCATION IN S:\\{STUDY_YEAR}\{ST}
DATA_ROOT = os.path.join(SDRIVE, STUDY_YEAR, STATE_ABR)



#------------------------------------------------------------------------------
# CUTS / DEMOGRAPHICS FILE-- STANDARD NAME
#------------------------------------------------------------------------------
CUTS_FILE = f"{STATE_ABR}_Cuts_Demographics_{STUDY_TYPE}.xlsx"

CUTS_DEMO_FILE = CUTS_DEMO_FILES / CUTS_FILE

print("CUTS_DEMO_FILE =", CUTS_DEMO_FILE)

if not CUTS_DEMO_FILE.exists():
    raise FileNotFoundError(
        f"Cuts file not found:\n{CUTS_DEMO_FILE}"
    )




#------------------------------------------------------------------------------
#  GET CUTS DEMOGRAPHICS DATA
#------------------------------------------------------------------------------

xl = pd.ExcelFile(CUTS_DEMO_FILE)

sheet_map = {
    s.lower(): s
    for s in xl.sheet_names
}

cuts_df = pd.read_excel(
    CUTS_DEMO_FILE,
    sheet_name=sheet_map['cut_scores'],
    skiprows=3
)

pop_input = pd.read_excel(
    CUTS_DEMO_FILE,
    sheet_name=sheet_map['pop_input']
)

race_mapping = pd.read_excel(
    CUTS_DEMO_FILE,
    sheet_name=sheet_map['race_mapping']
)



#------------------------------------------------------------------------------
# from snowflake get studysample_df 
#------------------------------------------------------------------------------

query = f"""
select    
    M_student_business_identifier, 
    m_test_event_business_identifier,
    m_student_gender,
    d_sex,
    m_nwea_ethnic_group_name,
    d_ethnicity,
    d_race,    
    d_grade_clean,   
    m_state,
    settings_term,
    D_plcode,
    d_pldesc,
    d_ss,
    d_subject,
    m_grade_ordinal,
    m_test_name,
    settings_study_type

from research_prd_grd_db.linking_studies.tx2026_studysample_qa

where match_type <> 'UNMATCHED'
  and D_ss is not null
  and settings_study_type = '{STUDY_TYPE}'

order by M_student_business_identifier
"""

studysample_df = query_snowflake(
    query,
    SNOWFLAKEUSER,
    ROLE,
    WAREHOUSE,
    DATABASE=DATABASE,
    SCHEMA=SCHEMA
)

print(f"Rows returned: {studysample_df.shape[0]:,}")
print(f"Columns returned: {studysample_df.shape[1]}")
print(studysample_df.columns.tolist())



#------------------------------------------------------------------------------
# MERGE TO CUTS TABLE
#------------------------------------------------------------------------------


#ADD LOSS HOSS
#------------------------------------------------------------------------------
# ADD LOSS / HOSS TO CUT SCORES
#------------------------------------------------------------------------------

if STUDY_TYPE in ['EOG', 'SP']:

    loss_hoss_groups = [
        'D_SUBJECT',
        'SUBJECT',
        'GRADE'
    ]

else:   # EOC / HS

    loss_hoss_groups = [
        'D_SUBJECT',
        'SUBJECT'
    ]


cuts_df['CUTS_LOSS'] = (
    cuts_df
    .groupby(loss_hoss_groups)['MIN']
    .transform('min')
)

cuts_df['CUTS_HOSS'] = (
    cuts_df
    .groupby(loss_hoss_groups)['MAX']
    .transform('max')
)



#---------------------------------------
# RENAME CUTS FIELDS FOR CLARITY
#---------------------------------------

cuts_df = cuts_df.rename(
    columns={
        'D_SUBJECT': 'CUTS_D_SUBJECT',
        'SUBJECT': 'CUTS_SUBJECT',
        'GRADE': 'CUTS_GRADE',
        'PROFICIENCY_LEVEL': 'CUTS_PROFICIENCY_LEVEL',
        'PROFICIENCY_NAME': 'CUTS_PROFICIENCY_NAME',
        'MIN': 'CUTS_MIN',
        'MAX': 'CUTS_MAX'
    }
)


#-----------------------------------------
#  EOC(HS) AND ANY STUDY THAT IS NOT
# LABELLED EOG OR SP IN CUTS FILE
# AND THIS CODE'S SETTINGS ABOVE
# WILL NOT USE GRADE IN MERGE CONDITIONS
#------------------------------------------  


if STUDY_TYPE in ['EOG', 'SP']:

    merged = pd.merge(
        studysample_df,
        cuts_df,
        how='inner',
        left_on=[
            'D_SUBJECT',
            'D_GRADE_CLEAN',
            'M_GRADE_ORDINAL'
        ],
        right_on=[
            'CUTS_D_SUBJECT',
            'CUTS_GRADE',
            'CUTS_SUBJECT'
        ]
    )

else:

    merged = pd.merge(
        studysample_df,
        cuts_df,
        how='inner',
        left_on=[
            'D_SUBJECT',
            'M_GRADE_ORDINAL'
        ],
        right_on=[
            'CUTS_D_SUBJECT',
            'CUTS_SUBJECT'
        ]
    )


merged = merged.loc[
    (merged['CUTS_MIN'] <= merged['D_SS'])
    &
    (merged['CUTS_MAX'] >= merged['D_SS'])
]


#------------------------------------------------------------------------------
# CREATE CUTS / DEMOGRAPHICS REVIEW WORKSHEETS
#------------------------------------------------------------------------------


#------------------------------------------------------------------------------
# OUTPUT FILE
#------------------------------------------------------------------------------

CUTS_DEMO_WORKSHEETS_FILE = (
    CUTS_DEMO_FILES / "cuts_demo_worksheets.xlsx"
)


#------------------------------------------------------------------------------
# STANDARDIZE SNOWFLAKE COLUMN NAMES
#
# pd.read_sql() usually returns uppercase Snowflake column names.
# Standardizing here makes the remaining code predictable.
#------------------------------------------------------------------------------

studysample_df.columns = (
    studysample_df.columns
    .str.strip()
    .str.upper()
)


#------------------------------------------------------------------------------
# HELPER: FIND AN EXCEL SHEET CASE-INSENSITIVELY
#------------------------------------------------------------------------------

def get_sheet_name_case_insensitive(excel_file, target_sheet):
    """
    Return the workbook's actual sheet name using a case-insensitive match.
    """

    sheet_lookup = {
        sheet_name.strip().casefold(): sheet_name
        for sheet_name in excel_file.sheet_names
    }

    target_key = target_sheet.strip().casefold()

    if target_key not in sheet_lookup:
        raise ValueError(
            f"Worksheet '{target_sheet}' was not found in:\n"
            f"{excel_file.io}\n\n"
            f"Available worksheets: {excel_file.sheet_names}"
        )

    return sheet_lookup[target_key]


#------------------------------------------------------------------------------
# READ CUT SCORES
#
# The first three rows are descriptive rows, so the table header begins
# on Excel row 4.
#------------------------------------------------------------------------------

cuts_excel = pd.ExcelFile(
    CUTS_DEMO_FILE,
    engine="openpyxl"
)

cuts_sheet_name = get_sheet_name_case_insensitive(
    cuts_excel,
    "Cut_scores"
)

cuts_df = pd.read_excel(
    cuts_excel,
    sheet_name=cuts_sheet_name,
    skiprows=3
)

cuts_df.columns = (
    cuts_df.columns
    .astype(str)
    .str.strip()
    .str.upper()
)


#------------------------------------------------------------------------------
# KEEP AND RENAME REQUIRED CUT-SCORE FIELDS
#------------------------------------------------------------------------------

required_cuts_columns = [
    "D_SUBJECT",
    "SUBJECT",
    "GRADE",
    "PROFICIENCY_LEVEL",
    "PROFICIENCY_NAME",
    "MIN",
    "MAX"
]

missing_cuts_columns = [
    column
    for column in required_cuts_columns
    if column not in cuts_df.columns
]

if missing_cuts_columns:
    raise KeyError(
        "The Cut_scores worksheet is missing required columns:\n"
        f"{missing_cuts_columns}\n\n"
        f"Available columns:\n{cuts_df.columns.tolist()}"
    )

cuts_df = cuts_df[required_cuts_columns].copy()

cuts_df = cuts_df.rename(
    columns={
        "D_SUBJECT": "CUTS_D_SUBJECT",
        "SUBJECT": "CUTS_SUBJECT",
        "GRADE": "CUTS_GRADE",
        "PROFICIENCY_LEVEL": "CUTS_PROFICIENCY_LEVEL",
        "PROFICIENCY_NAME": "CUTS_PROFICIENCY_NAME",
        "MIN": "CUTS_MIN",
        "MAX": "CUTS_MAX"
    }
)


#------------------------------------------------------------------------------
# STANDARDIZE MERGE FIELDS
#------------------------------------------------------------------------------

studysample_df["D_SUBJECT"] = (
    studysample_df["D_SUBJECT"]
    .astype("string")
    .str.strip()
)

cuts_df["CUTS_D_SUBJECT"] = (
    cuts_df["CUTS_D_SUBJECT"]
    .astype("string")
    .str.strip()
)

studysample_df["D_GRADE_CLEAN"] = pd.to_numeric(
    studysample_df["D_GRADE_CLEAN"],
    errors="coerce"
).astype("Int64")

cuts_df["CUTS_GRADE"] = pd.to_numeric(
    cuts_df["CUTS_GRADE"],
    errors="coerce"
).astype("Int64")

studysample_df["D_SS"] = pd.to_numeric(
    studysample_df["D_SS"],
    errors="coerce"
)

cuts_df["CUTS_MIN"] = pd.to_numeric(
    cuts_df["CUTS_MIN"],
    errors="coerce"
)

cuts_df["CUTS_MAX"] = pd.to_numeric(
    cuts_df["CUTS_MAX"],
    errors="coerce"
)


#------------------------------------------------------------------------------
# MERGE EACH STUDENT RECORD TO ALL CUT BANDS FOR ITS SUBJECT AND GRADE
#------------------------------------------------------------------------------

studysample_withcuts = pd.merge(
    studysample_df,
    cuts_df,
    how="left",
    left_on=[
        "D_SUBJECT",
        "D_GRADE_CLEAN"
    ],
    right_on=[
        "CUTS_D_SUBJECT",
        "CUTS_GRADE"
    ],
    indicator="CUTS_MERGE_STATUS"
)


# #------------------------------------------------------------------------------
# # KEEP THE CUT BAND CONTAINING THE STUDENT'S STATE SCALE SCORE
# #------------------------------------------------------------------------------

# score_in_cut_range = (
#     studysample_withcuts["D_SS"].ge(
#         studysample_withcuts["CUTS_MIN"]
#     )
#     &
#     studysample_withcuts["D_SS"].le(
#         studysample_withcuts["CUTS_MAX"]
#     )
# )

# studysample_withcuts = (
#     studysample_withcuts
#     .loc[score_in_cut_range]
#     .copy()
# )


# #------------------------------------------------------------------------------
# # RACE / ETHNICITY REVIEW TAB
# #------------------------------------------------------------------------------

# race = (
#     studysample_withcuts[
#         [
#             "M_NWEA_ETHNIC_GROUP_NAME",
#             "D_ETHNICITY",
#             "D_RACE"
#         ]
#     ]
#     .value_counts(dropna=False)
#     .reset_index(name="COUNT")
#     .sort_values(
#         by=[
#             "D_ETHNICITY",
#             "D_RACE",
#             "M_NWEA_ETHNIC_GROUP_NAME"
#         ],
#         na_position="last"
#     )
#     .reset_index(drop=True)
# )

# # Fields to complete during manual review
# race["RACE"] = ""
# race["RACE_DESC"] = ""


# #------------------------------------------------------------------------------
# # SEX / GENDER REVIEW TAB
# #------------------------------------------------------------------------------

# sex = (
#     studysample_withcuts[
#         [
#             "M_STUDENT_GENDER",
#             "D_SEX"
#         ]
#     ]
#     .value_counts(dropna=False)
#     .reset_index(name="COUNT")
#     .sort_values(
#         by=[
#             "D_SEX",
#             "M_STUDENT_GENDER"
#         ],
#         na_position="last"
#     )
#     .reset_index(drop=True)
# )

# # Final numeric study-sample sex value
# sex["SEX"] = ""


# #------------------------------------------------------------------------------
# # PERFORMANCE-LEVEL REVIEW TAB
# #
# # Shows district-provided PL beside the score-derived cuts PL.
# #------------------------------------------------------------------------------

# pl = (
#     studysample_withcuts[
#         [
#             "D_SUBJECT",
#             "M_SUBJECT",
#             "D_GRADE_CLEAN",
#             "M_TEST_NAME",
#             "D_PLCODE",
#             "D_PLDESC",
#             "CUTS_PROFICIENCY_LEVEL",
#             "CUTS_PROFICIENCY_NAME",
#             "CUTS_MIN",
#             "CUTS_MAX"
#         ]
#     ]
#     .value_counts(dropna=False)
#     .reset_index(name="COUNT")
#     .sort_values(
#         by=[
#             "D_SUBJECT",
#             "M_SUBJECT",
#             "D_GRADE_CLEAN",
#             "CUTS_PROFICIENCY_LEVEL",
#             "D_PLCODE"
#         ],
#         na_position="last"
#     )
#     .reset_index(drop=True)
# )

# # Final reviewed values
# pl["PL_CODE"] = ""
# pl["PL_DESC"] = ""


# #------------------------------------------------------------------------------
# # PL-BY-DISTRICT REVIEW TAB
# #
# # Your current query does not include a district field. This tab will be
# # produced when D_DISTRICTNAME is added to the Snowflake SELECT.
# #------------------------------------------------------------------------------

# if "D_DISTRICTNAME" in studysample_withcuts.columns:

#     pl_district = (
#         studysample_withcuts[
#             [
#                 "D_DISTRICTNAME",
#                 "D_SUBJECT",
#                 "M_SUBJECT",
#                 "D_GRADE_CLEAN",
#                 "M_TEST_NAME",
#                 "D_PLCODE",
#                 "D_PLDESC",
#                 "CUTS_PROFICIENCY_LEVEL",
#                 "CUTS_PROFICIENCY_NAME",
#                 "CUTS_MIN",
#                 "CUTS_MAX"
#             ]
#         ]
#         .value_counts(dropna=False)
#         .reset_index(name="COUNT")
#         .sort_values(
#             by=[
#                 "D_DISTRICTNAME",
#                 "D_SUBJECT",
#                 "M_SUBJECT",
#                 "D_GRADE_CLEAN",
#                 "CUTS_PROFICIENCY_LEVEL"
#             ],
#             na_position="last"
#         )
#         .reset_index(drop=True)
#     )

#     pl_district["PL_CODE"] = ""
#     pl_district["PL_DESC"] = ""

# else:

#     pl_district = pd.DataFrame(
#         {
#             "MESSAGE": [
#                 "D_DISTRICTNAME was not included in the Snowflake query. "
#                 "Add it to the SELECT clause to populate this worksheet."
#             ]
#         }
#     )


# #------------------------------------------------------------------------------
# # OPTIONAL CUT-MERGE QA TAB
# #
# # Identifies Snowflake records for which no valid subject/grade/score band
# # was found. This is useful for LOSS/HOSS and cuts-file troubleshooting.
# #------------------------------------------------------------------------------

# records_with_valid_cut = set(
#     studysample_withcuts["M_TEST_EVENT_BUSINESS_IDENTIFIER"]
#     .dropna()
#     .astype(str)
# )

# cuts_merge_qa = (
#     studysample_df.loc[
#         ~studysample_df[
#             "M_TEST_EVENT_BUSINESS_IDENTIFIER"
#         ].astype(str).isin(records_with_valid_cut),
#         [
#             "M_STUDENT_BUSINESS_IDENTIFIER",
#             "M_TEST_EVENT_BUSINESS_IDENTIFIER",
#             "D_SUBJECT",
#             "D_GRADE_CLEAN",
#             "D_SS",
#             "D_PLCODE",
#             "D_PLDESC"
#         ]
#     ]
#     .copy()
# )

# cuts_merge_qa["QA_REASON"] = (
#     "No matching subject/grade/cut-score range"
# )


# #------------------------------------------------------------------------------
# # CREATE OUTPUT FOLDER IF NECESSARY
# #------------------------------------------------------------------------------

# CUTS_DEMO_FILES.mkdir(
#     parents=True,
#     exist_ok=True
# )


# #------------------------------------------------------------------------------
# # EXPORT REVIEW WORKBOOK
# #------------------------------------------------------------------------------

# with pd.ExcelWriter(
#     CUTS_DEMO_WORKSHEETS_FILE,
#     engine="openpyxl",
#     mode="w"
# ) as writer:

#     race.to_excel(
#         writer,
#         sheet_name="raw_Race_and_eth",
#         index=False
#     )

#     pl.to_excel(
#         writer,
#         sheet_name="raw_PL",
#         index=False
#     )

#     pl_district.to_excel(
#         writer,
#         sheet_name="raw_pl_by_district",
#         index=False
#     )

#     sex.to_excel(
#         writer,
#         sheet_name="raw_sex",
#         index=False
#     )

#     cuts_merge_qa.to_excel(
#         writer,
#         sheet_name="cuts_merge_QA",
#         index=False
#     )

#     # Basic review-friendly formatting
#     for worksheet in writer.book.worksheets:

#         worksheet.freeze_panes = "A2"
#         worksheet.auto_filter.ref = worksheet.dimensions

#         for column_cells in worksheet.columns:
#             values = [
#                 "" if cell.value is None else str(cell.value)
#                 for cell in column_cells
#             ]

#             width = min(
#                 max(
#                     len(value)
#                     for value in values
#                 ) + 2,
#                 40
#             )

#             worksheet.column_dimensions[
#                 column_cells[0].column_letter
#             ].width = width


# print()
# print("Cuts/demo review workbook created:")
# print(CUTS_DEMO_WORKSHEETS_FILE)
# print()

# print("Worksheet row counts:")
# print(f"  raw_Race_and_eth:    {len(race):,}")
# print(f"  raw_PL:              {len(pl):,}")
# print(f"  raw_pl_by_district:  {len(pl_district):,}")
# print(f"  raw_sex:             {len(sex):,}")
# print(f"  cuts_merge_QA:       {len(cuts_merge_qa):,}")