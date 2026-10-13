# -*- coding: utf-8 -*-
"""
Created on Fri Oct  2 22:31:53 2026

@author: Chris.Wells
"""



from pathlib import Path
import re
import pandas as pd
from typing import Optional
import sys
import os
from snowflake.connector.pandas_tools import write_pandas

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



#------------------------------------------------------------------------------
#  STANDARD PATHS AND FILES
#------------------------------------------------------------------------------

# STANDARD LOCATION IN S:\\{STUDY_YEAR}\{ST}
DATA_ROOT = os.path.join(SDRIVE, STUDY_YEAR, STATE_ABR)


# NAME OF SNWFLAKE TABLES TO LOAD COMPLETED WORKSHEETS
# FOR MERGING ADJUSTED FIELDS BACK TO DATA
sex_table_name =  f"{STATE_ABR}{STUDY_YEAR}_worksheet_sex_{STUDY_TYPE}"
pl_table_name =  f"{STATE_ABR}{STUDY_YEAR}_worksheet_pl_{STUDY_TYPE}"
race_table_name =  f"{STATE_ABR}{STUDY_YEAR}_worksheet_race_{STUDY_TYPE}"
pre_worksheet_scores_table_name = f"{STATE_ABR}{STUDY_YEAR}_pre_worksheet_scores_{STUDY_TYPE}"


sex_table_name.replace('"', '')
pl_table_name.replace('"', '')
race_table_name.replace('"', '')

print(repr(race_table_name))

#------------------------------------------------------------------------------
# CUTS / DEMOGRAPHICS FILE-- STANDARD NAME
#------------------------------------------------------------------------------

# STANDARD
CUTS_FILE = f"{STATE_ABR}_Cuts_Demographics_{STUDY_TYPE}.xlsx"

CUTS_DEMO_FILE = CUTS_DEMO_FILES / CUTS_FILE

print("CUTS_DEMO_FILE =", CUTS_DEMO_FILE)

if not CUTS_DEMO_FILE.exists():
    raise FileNotFoundError(
        f"Cuts file not found:\n{CUTS_DEMO_FILE}"
    )
    


#------------------------------------------------------------------------------
# CUTS / DEMOGRAPHICS FILE-- NON-STANDARD
#------------------------------------------------------------------------------
    
CUTS_FILE = f"{STATE_ABR}_Cuts_Demographics_{STUDY_TYPE}_cw.xlsx"

CUTS_DEMO_FILE = os.path.join(
    DATA_ROOT,
    'cuts_demo_files',
    CUTS_FILE
)



#------------------------------------------------------------------------------
# CUTS_DEMO_WORKSHEETS_FILE
#------------------------------------------------------------------------------
CUTS_DEMO_WORKSHEETS_FILE = CUTS_DEMO_FILES / (
    f"{STATE_ABR}_Cuts_Demographic_Worksheets_{STUDY_TYPE}.xlsx"
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
select *

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
# ADD LOSS / HOSS TO CUT SCORES  EOG dif from EOC
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
# EOC(HS) AND ANY STUDY THAT IS NOT
# LABELLED EOG OR SP IN CUTS FILE
# AND THIS CODE'S SETTINGS ABOVE
# WILL NOT USE GRADE IN MERGE CONDITIONS
#------------------------------------------  

#prep strings for merge
studysample_df['D_SUBJECT'] = studysample_df['D_SUBJECT'].astype(str).str.strip().str.upper()
cuts_df['CUTS_D_SUBJECT'] = cuts_df['CUTS_D_SUBJECT'].astype(str).str.strip().str.upper()



# ------------------------------------------------------------
# Add a temporary unique identifier to each study-sample row.
# This lets us determine whether each original row ultimately
# matches exactly one cuts record.
# ------------------------------------------------------------
studysample_for_merge = (
    studysample_df
    .reset_index(drop=True)
    .copy()
)

studysample_for_merge['_STUDY_ROW_ID'] = studysample_for_merge.index


# ------------------------------------------------------------
# Merge the study sample with all potentially applicable cuts.
# Use a left merge so unmatched study-sample rows are retained
# long enough to be written to the QA file.
#
# EOG by subject/grade/map_subject-- should be unique
# EOC by subject/map_subject-- should be unique 
#         (ENG2 vs. Eng1) will distinguish these two
#         (1 vs 100) will distinguisch alg-alg vs. alg-math
#
# This will be the exploded merge prior to cuts applied to data. 
# ------------------------------------------------------------
if STUDY_TYPE in ['EOG', 'SP']:

    cuts_merge = pd.merge(
        studysample_for_merge,
        cuts_df,
        how='left',
        left_on=[
            'D_SUBJECT',
            'D_GRADE_CLEAN',
            'M_MEASUREMENT_SCALE_BID'
        ],
        right_on=[
            'CUTS_D_SUBJECT',
            'CUTS_GRADE',
            'CUTS_SUBJECT'
        ],
        indicator=True
    )

else:

    cuts_merge = pd.merge(
        studysample_for_merge,
        cuts_df,
        how='left',
        left_on=[
            'D_SUBJECT',
            'M_MEASUREMENT_SCALE_BID'
        ],
        right_on=[
            'CUTS_D_SUBJECT',
            'CUTS_SUBJECT'
        ],
        indicator=True
    )


# ------------------------------------------------------------
# Create SS_ADJ.
#
# D_SS below LOSS  -> SS_ADJ = LOSS
# D_SS above HOSS  -> SS_ADJ = HOSS
# Otherwise         -> SS_ADJ = D_SS
# ------------------------------------------------------------
cuts_merge['SS_ADJ'] = cuts_merge['D_SS'].clip(
    lower=cuts_merge['CUTS_LOSS'],
    upper=cuts_merge['CUTS_HOSS']
)


# ------------------------------------------------------------
# Identify cuts rows for which the adjusted score falls within
# the inclusive CUTS_MIN/CUTS_MAX range.
# ------------------------------------------------------------
cuts_merge['_QUALIFIES_FOR_CUT'] = (
    cuts_merge['_merge'].eq('both')
    & cuts_merge['SS_ADJ'].notna()
    & cuts_merge['SS_ADJ'].between(
        cuts_merge['CUTS_MIN'],
        cuts_merge['CUTS_MAX'],
        inclusive='both'
    )
)


# ------------------------------------------------------------
# Count the number of qualifying cuts rows for each original
# study-sample row.
# ------------------------------------------------------------
qualifying_counts = (
    cuts_merge.loc[cuts_merge['_QUALIFIES_FOR_CUT']]
    .groupby('_STUDY_ROW_ID')
    .size()
    .rename('CUTS_MATCH_COUNT')
)


studysample_for_merge = studysample_for_merge.merge(
    qualifying_counts,
    how='left',
    left_on='_STUDY_ROW_ID',
    right_index=True
)

studysample_for_merge['CUTS_MATCH_COUNT'] = (
    studysample_for_merge['CUTS_MATCH_COUNT']
    .fillna(0)
    .astype(int)
)


# ----------------------------------------------------------------
# Create QA output for original study-sample rows that did not
# qualify against exactly one cuts record.

# these don't match due to gaps in the cuts e.g 
# pl 2 max = 300 but pl 3 min = 310.  301,302,303... don't merge

# appears to be indication of problematic file/grade incorrect
# 
# ----------------------------------------------------------------
qa_dropped_from_cuts = studysample_for_merge.loc[
    studysample_for_merge['CUTS_MATCH_COUNT'].ne(1)
].copy()


# Explain why each record was dropped
qa_dropped_from_cuts['CUTS_DROP_REASON'] = 'Did not qualify for a cuts range'

qa_dropped_from_cuts.loc[
    qa_dropped_from_cuts['CUTS_MATCH_COUNT'].eq(0),
    'CUTS_DROP_REASON'
] = 'No qualifying cuts record'

qa_dropped_from_cuts.loc[
    qa_dropped_from_cuts['CUTS_MATCH_COUNT'].gt(1),
    'CUTS_DROP_REASON'
] = 'Matched more than one cuts record'



#------------------------------------------------
# QA dropped Reason-- no qualifying cuts record
# should only exist if gaps exist in cuts data
#-----------------------------------------------
qa_dropped_from_cuts['CUTS_DROP_REASON'].value_counts(dropna = False)


#district problem?-- maybe grade wrong or subjects out or order?
qa_dropped_from_cuts[['D_DISTRICTNAME','D_AGENCYCODE']].value_counts()





# ------------------------------------------------------------
# Keep only the cuts rows that:
#   1. Qualify using SS_ADJ, and
#   2. Belong to a study row with exactly one qualifying cut.
#
#  qa-  merged may have fewer rows than studysample_df 
# ------------------------------------------------------------
valid_study_row_ids = studysample_for_merge.loc[
    studysample_for_merge['CUTS_MATCH_COUNT'].eq(1),
    '_STUDY_ROW_ID'
]

merged = cuts_merge.loc[
    cuts_merge['_QUALIFIES_FOR_CUT']
    & cuts_merge['_STUDY_ROW_ID'].isin(valid_study_row_ids)
].copy()


# ------------------------------------------------------------
# Write QA file and issue console warning when records dropped.
# ------------------------------------------------------------

QA_DROPPED_FROM_CUTS_FILE = os.path.join(
    DATA_ROOT,
    'qa_dropped_from_cuts.xlsx'
)




if not qa_dropped_from_cuts.empty:

    qa_dropped_from_cuts = qa_dropped_from_cuts.sort_values(
        ['D_SUBJECT', 'D_GRADE_CLEAN']
    ).reset_index(drop=True)

    # Remove timezone information from any datetime columns
    for col in qa_dropped_from_cuts.select_dtypes(include=['datetimetz']).columns:
        qa_dropped_from_cuts[col] = qa_dropped_from_cuts[col].dt.tz_localize(None)

    qa_dropped_from_cuts.to_excel(
        QA_DROPPED_FROM_CUTS_FILE,
        index=False
    )

    warning_message = (
        f"WARNING: {len(qa_dropped_from_cuts):,} study-sample "
        f"record(s) were dropped during the merge to cut scores. "
        f"QA file written to: {QA_DROPPED_FROM_CUTS_FILE}"
    )

    print("\n" + "=" * 80)
    print("WARNING")
    print(warning_message)
    print("=" * 80 + "\n")

else:

    print(
        "All study-sample records matched exactly one qualifying "
        "cut-score record."
    )


# ------------------------------------------------------------
# Remove temporary QA/helper fields from final merged dataframe.
# SS_ADJ is intentionally retained.
# ------------------------------------------------------------
merged = merged.drop(
    columns=[
        '_STUDY_ROW_ID',
        '_merge',
        '_QUALIFIES_FOR_CUT'
    ],
    errors='ignore'
).reset_index(drop=True)


print(f"final merged records: {len(merged):,}")
print(f"Dropped study-sample records: {len(qa_dropped_from_cuts):,}")


#-------------------------------------------------------------------------
# Populate proficiency fields from cuts lookup
#-------------------------------------------------------------------------
merged['PL_CODE'] = merged['CUTS_PROFICIENCY_LEVEL']
merged['PL_DESC'] = merged['CUTS_PROFICIENCY_NAME']



#------------------------------------------------------------------------------

# I think unnecesary now that whole studysample is dowloaded to update.

# CREATE SCORES TO MERGE BACK TO DATA
# RECORDS THAT DID NOT DROP WILL HAVE SS_ADJ TO MERGE BACK
# ALSO pl_code AND pl_desc --> all of THESE MAY BE UPDATED BY WORKSHEETS BELOW.
# NONE of these fields yet exist in studysample_qa.
#------------------------------------------------------------------------------
pre_worksheet_scores = merged[['M_TEST_EVENT_BUSINESS_IDENTIFIER',
                 'D_SUBJECT', 
                 'M_MEASUREMENT_SCALE_BID',
                 'SS_ADJ',
                 'PL_CODE',
                 'PL_DESC'                 
                 ]]





#==============================================================================
#==============================================================================
# CREATE CUTS / DEMOGRAPHICS REVIEW WORKSHEETS
#==============================================================================
#==============================================================================

#==============================================================================
# PREPARE AND OUTPUT RACE / PL / SEX REVIEW WORKBOOK
#==============================================================================


#------------------------------------------------------------------------------
# USE FINAL MERGED DATA
#------------------------------------------------------------------------------

studysample_withcuts = merged.copy()



#QA Counts
merged[['M_STUDENT_GENDER',	'D_SEX']].value_counts()

studysample_withcuts[['M_STUDENT_GENDER',	'D_SEX']].value_counts()



#------------------------------------------------------------------------------
# RACE REVIEW
#------------------------------------------------------------------------------
#
# Create unique review patterns and assign a review marker.
# The marker is then merged back to ALL matching study-sample rows.
#------------------------------------------------------------------------------

race = (
    studysample_withcuts[
        [
            'M_NWEA_ETHNIC_GROUP_NAME',
            'D_ETHNICITY',
            'D_RACE'
        ]
    ]
    .value_counts(dropna=False)
    .reset_index(name='count')
    .sort_values(
        [
            'D_ETHNICITY',
            'D_RACE',
            'M_NWEA_ETHNIC_GROUP_NAME'
        ],
        na_position='last'
    )
    .reset_index(drop=True)
)

#-------------------------------------------------------------
# Create review marker
#-------------------------------------------------------------

race['RACE_REVIEW_MARKER'] = (
    'R'
    + (race.index + 1).astype(str)
)

#-------------------------------------------------------------
# Final race fields to be manually populated during review
#-------------------------------------------------------------

race['RACE'] = ''
race['RACE_DESC'] = ''



#-------------------------------------------------------------
# Put marker first in worksheet
#-------------------------------------------------------------

race = race[
    [
        'RACE_REVIEW_MARKER',
        'M_NWEA_ETHNIC_GROUP_NAME',
        'D_ETHNICITY',
        'D_RACE',
        'count',
        'RACE',
        'RACE_DESC'
    ]
]

#-------------------------------------------------------------
# Merge marker back to ALL matching study sample rows
#-------------------------------------------------------------

studysample_withcuts = studysample_withcuts.merge(
    race[
        [
            'RACE_REVIEW_MARKER',
            'M_NWEA_ETHNIC_GROUP_NAME',
            'D_ETHNICITY',
            'D_RACE'
        ]
    ],
    on=[
        'M_NWEA_ETHNIC_GROUP_NAME',
        'D_ETHNICITY',
        'D_RACE'
    ],
    how='left'
)




#------------------------------------------------------------------------------
# PL REVIEW
#
# Includes the incoming district PL field when it is available.
#------------------------------------------------------------------------------

# pl_columns = [
#     'D_SUBJECT',
#     'D_GRADE_CLEAN',
#     'CUTS_PROFICIENCY_LEVEL',
#     'CUTS_PROFICIENCY_NAME',
#     'PL_CODE',
#     'PL_DESC'
# ]


# # Include these optional source columns when present

# optional_pl_columns = [
#     'M_SUBJECT',
#     'D_PL'
# ]

# for column in optional_pl_columns:
#     if column in studysample_withcuts.columns:
#         pl_columns.insert(2, column)


# pl = (
#     studysample_withcuts[pl_columns]
#     .value_counts(dropna=False)
#     .reset_index(name='count')
#     .sort_values(
#         [
#             'D_SUBJECT',
#             'D_GRADE_CLEAN',
#             'PL_CODE'
#         ],
#         na_position='last'
#     )
#     .reset_index(drop=True)
# )


#------------------------------------------------------------------------------
# PL REVIEW BY DISTRICT
#------------------------------------------------------------------------------

pl_district_columns = [
    'D_AGENCYCODE',
    'D_DISTRICTNAME',
    # 'D_SUBJECT',
    # 'D_GRADE_CLEAN',
    'D_PLCODE',
    'D_PLDESC',    
    'PL_CODE',
    'PL_DESC'
]


# for column in optional_pl_columns:
#     if column in studysample_withcuts.columns:
#         pl_district_columns.insert(3, column)


pl_district = (
    studysample_withcuts[pl_district_columns]
    .value_counts(dropna=False)
    .reset_index(name='count')
    .sort_values(
        [
            'D_AGENCYCODE',
            'D_DISTRICTNAME',
            # 'D_SUBJECT',
            # 'D_GRADE_CLEAN',           
            'PL_CODE',
            'PL_DESC'
        ],
        na_position='last'
    )
    .reset_index(drop=True)
)


#------------------------------------------------------------------------------
# PL CODE REVIEW
#
# Compare district PL to cuts-derived PL.
# Create a review marker that can be merged back later.
#------------------------------------------------------------------------------


pl_code = (
    studysample_withcuts[
        [
            # 'D_SUBJECT',
            # 'D_GRADE_CLEAN',
            'D_PLCODE',
            'D_PLDESC',
            'PL_CODE',
            'PL_DESC'
        ]
    ]
    .value_counts(dropna=False)
    .reset_index(name='COUNT')
    .sort_values(
        [
            # 'D_SUBJECT',
            # 'D_GRADE_CLEAN',            
            'D_PLCODE',
            'D_PLDESC',
            'PL_CODE',
            'PL_DESC'
        ],
        na_position='last'
    )
    .reset_index(drop=True)
)

# Unique marker for each complete PL pattern
pl_code['PL_REVIEW_MARKER'] = (
    'P'
    + (pl_code.index + 1).astype(str)
)

# Put marker first and count last
pl_code = pl_code[
    [
        'PL_REVIEW_MARKER',
        # 'D_SUBJECT',
        # 'D_GRADE_CLEAN',
        'D_PLCODE',
        'D_PLDESC',
        'COUNT',
        'PL_CODE',
        'PL_DESC',
        
    ]
]

# reviewer edits THESE fields
pl_code['REVIEWED_PL_CODE'] = pl_code['PL_CODE']
pl_code['REVIEWED_PL_DESC'] = pl_code['PL_DESC']

#  ** INSTEAD, EDIT THE PL_CODE AND PL_DESC DIRECTLY***

#-------------------------------------------------------------
# Merge PL review marker back to study sample
#-------------------------------------------------------------

studysample_withcuts = studysample_withcuts.merge(
    pl_code[
        [
            'PL_REVIEW_MARKER',
            # 'D_SUBJECT',
            # 'D_GRADE_CLEAN',
            'D_PLCODE',
            'D_PLDESC',
            'COUNT',
            'PL_CODE',
            'PL_DESC',
            'REVIEWED_PL_CODE',
            'REVIEWED_PL_DESC'
            
    ]],
    on=[        
        # 'D_SUBJECT',
        # 'D_GRADE_CLEAN',
        'D_PLCODE',
        'D_PLDESC',
        'PL_CODE',
        'PL_DESC'
    ],
    how='left'
)





#------------------------------------------------------------------------------
# SEX REVIEW
#
# Use M_STUDENT_GENDER when present. Fall back to M_SEX for datasets that
# still use the older field name.
#------------------------------------------------------------------------------

if 'M_STUDENT_GENDER' in studysample_withcuts.columns:
    nwea_sex_column = 'M_STUDENT_GENDER'

elif 'M_SEX' in studysample_withcuts.columns:
    nwea_sex_column = 'M_SEX'

else:
    raise KeyError(
        "Neither M_STUDENT_GENDER nor M_SEX was found in the merged dataframe."
    )

sex = (
    studysample_withcuts[
        [
            nwea_sex_column,
            'D_SEX'
        ]
    ]
    .value_counts(dropna=False)
    .reset_index(name='count')
    .sort_values(
        [
            'D_SEX',
            nwea_sex_column
        ],
        na_position='last'
    )
    .reset_index(drop=True)
)

#-------------------------------------------------------------
# Create review marker
#-------------------------------------------------------------

sex['SEX_REVIEW_MARKER'] = (
    'S'
    + (sex.index + 1).astype(str)
)

#-------------------------------------------------------------
# Final sex field to be manually populated during review
#-------------------------------------------------------------

sex['SEX'] = ''

#-------------------------------------------------------------
# Put marker first in worksheet
#-------------------------------------------------------------

sex = sex[
    [
        'SEX_REVIEW_MARKER',
        nwea_sex_column,
        'D_SEX',
        'count',
        'SEX'
    ]
]

#-------------------------------------------------------------
# Merge marker back to ALL matching study sample rows
#-------------------------------------------------------------

studysample_withcuts = studysample_withcuts.merge(
    sex[
        [
            'SEX_REVIEW_MARKER',
            nwea_sex_column,
            'D_SEX'
        ]
    ],
    on=[
        nwea_sex_column,
        'D_SEX'
    ],
    how='left'
)

#==============================================================================
# OUTPUT REVIEW WORKBOOK
#==============================================================================

# Keep only columns 1 and 2 from race_mapping
race_mapping_output = race_mapping.iloc[:, 0:2].copy()


output_dict = {
    # 'raw_PL': pl,
    'raw_pl_by_district': pl_district,
    'PL_code': pl_code,
    'raw_sex': sex
}


if not os.path.exists(CUTS_DEMO_WORKSHEETS_FILE):

    print()
    print('Outputting Cuts/Demo Review Workbook:')
    print(CUTS_DEMO_WORKSHEETS_FILE)
    print()

    with pd.ExcelWriter(
        CUTS_DEMO_WORKSHEETS_FILE,
        engine='openpyxl'
    ) as writer:

        #--------------------------------------------------------------
        # RACE WORKSHEET
        #
        # Write race data on the left.
        # Write the first two race_mapping columns on the right,
        # leaving two blank Excel columns between the tables.
        #--------------------------------------------------------------

        race.to_excel(
            writer,
            sheet_name='raw_Race_and_eth',
            index=False,
            startrow=0,
            startcol=0
        )

        race_mapping_start_column = len(race.columns) + 2

        race_mapping_output.to_excel(
            writer,
            sheet_name='raw_Race_and_eth',
            index=False,
            startrow=0,
            startcol=race_mapping_start_column
        )

        #--------------------------------------------------------------
        # REMAINING WORKSHEETS
        #--------------------------------------------------------------

        for sheet_name, dataframe in output_dict.items():

            dataframe.to_excel(
                writer,
                sheet_name=sheet_name,
                index=False
            )

    print('Cuts/Demo Review Workbook successfully created.')
    print()


else:

    print()
    print(
        'Cuts/Demo Review Workbook already exists and will not '
        'be overwritten:'
    )
    print(CUTS_DEMO_WORKSHEETS_FILE)
    print()
    
    
    
#=============================================================================
# PART 2-- manually EDIT THE ABOVE WORKSHEETS IF NECESSARY.
# THEN HIT ENTER TO RESUME.
#=============================================================================

print("/n SETP 1 complete. Please edit the Excel file now.")
input("Press Enter to continue to Step 2...")

#=============================================================================
# PART 2-- manually EDIT THE ABOVE WORKSHEETS IF NECESSARY.
# THEN HIT ENTER TO RESUME.
#=============================================================================


# ==============================================================
# RE-IMPORT MANUALLY EDITED SHEETS
# ==============================================================

# TEMP-- REGULAR FILES BLOCKED FOR EDIT OR RENAME.
# CUTS_DEMP_WORKSHEETS_FILE = r'S:\MAPGrowth\Linking\Data Files\2026\TX\cuts_demo_files\TX_Cuts_Demographic_Worksheets_EOG_edited.xlsx'

race_worksheet = pd.read_excel(
    CUTS_DEMO_WORKSHEETS_FILE,
    sheet_name='raw_Race_and_eth',
    dtype=str
).iloc[:, :8]


pl_worksheet = pd.read_excel(
    CUTS_DEMO_WORKSHEETS_FILE,
    sheet_name='PL_code',
    dtype=str
)

sex_worksheet = pd.read_excel(
    CUTS_DEMO_WORKSHEETS_FILE,
    sheet_name='raw_sex',
    dtype=str
)



# ----------------------------------------------------------
# UPLOAD MANUALLY EDITED WORKSHEETS TO SNOWFLAKE
#
# THIS WAS TO MERGE WORKSHEET EDITS INTO STUDYSAMPLE IN 
# SNOWFLAKE.
#
# MAYBE NOT NECESSARY NOW AS WHOLE STUDYSAMPLE_QA IS BEING
# DONWLOADED FOR UPDATES FROM WORKSHEETS.
# ----------------------------------------------------------



# CONN = establish_snowflake_connector(
#     SNOWFLAKEUSER,
#     ROLE,
#     WAREHOUSE,
#     DATABASE=DATABASE,
#     SCHEMA=SCHEMA
# )


# #----------------------------------------------------------
# #  pre_worksheet_scores
# #----------------------------------------------------------
# success, nchunks, nrows, _ = write_pandas(
#     CONN,
#     pre_worksheet_scores,
#     table_name=pre_worksheet_scores_table_name,
#     quote_identifiers=False,
#     overwrite=True,
#     auto_create_table=True
# )

# print(f"{pre_worksheet_scores}: {nrows:,} rows")


# #----------------------------------------------------------
# # SEX
# #----------------------------------------------------------
# success, nchunks, nrows, _ = write_pandas(
#     CONN,
#     sex_worksheet,
#     table_name=sex_table_name,
#     quote_identifiers=False,
#     overwrite=True,
#     auto_create_table=True
# )

# print(f"{sex_table_name}: {nrows:,} rows")


# #----------------------------------------------------------
# # PL
# #----------------------------------------------------------
# success, nchunks, nrows, _ = write_pandas(
#     CONN,
#     pl_worksheet,
#     table_name=pl_table_name,
#     quote_identifiers=False,
#     overwrite=True,
#     auto_create_table=True
# )

# print(f"{pl_table_name}: {nrows:,} rows")


# #----------------------------------------------------------
# # RACE
# #----------------------------------------------------------
# success, nchunks, nrows, _ = write_pandas(
#     CONN,
#     race_worksheet,
#     table_name=race_table_name,
#     quote_identifiers=False,
    
#     overwrite=True,
#     auto_create_table=True
# )

# print(f"{race_table_name}: {nrows:,} rows")


# CONN.commit()
# CONN.close()

# print("Worksheet uploads complete.")






#==============================================================================
# UPDATING STUDYSAMPE_WITHCUTS HERE
#==============================================================================




#==============================================================================
# UPDATE STUDYSAMPLE_WITHCUTS USING REVIEW MARKERS
#
# Each worksheet marker must identify exactly one worksheet row.
# Mapping by marker does not change the number of study-sample rows.
#==============================================================================

starting_row_count = len(studysample_withcuts)


def clean_marker_column(dataframe, marker_column):

    if marker_column not in dataframe.columns:
        raise KeyError(
            f"{marker_column} was not found in the dataframe."
        )

    dataframe[marker_column] = (
        dataframe[marker_column]
        .astype('string')
        .str.strip()
        .replace('', pd.NA)
    )


def validate_marker_lookup(
    worksheet,
    marker_column,
    value_columns
):

    missing_columns = [
        column
        for column in [marker_column] + value_columns
        if column not in worksheet.columns
    ]

    if missing_columns:
        raise KeyError(
            f"Worksheet is missing required columns: "
            f"{missing_columns}"
        )

    missing_markers = worksheet[
        worksheet[marker_column].isna()
    ]

    if not missing_markers.empty:
        raise ValueError(
            f"{len(missing_markers):,} worksheet row(s) have a "
            f"missing {marker_column}."
        )

    duplicate_markers = worksheet[
        worksheet.duplicated(
            subset=[marker_column],
            keep=False
        )
    ].copy()

    if not duplicate_markers.empty:

        conflicting_markers = (
            duplicate_markers
            .groupby(
                marker_column,
                dropna=False
            )[value_columns]
            .nunique(dropna=False)
            .gt(1)
            .any(axis=1)
        )

        conflicting_markers = (
            conflicting_markers[
                conflicting_markers
            ]
            .index
            .tolist()
        )

        if conflicting_markers:
            raise ValueError(
                f"Conflicting worksheet values were found for "
                f"{marker_column}: {conflicting_markers}"
            )

        worksheet = worksheet.drop_duplicates(
            subset=[marker_column],
            keep='first'
        ).copy()

    return worksheet


def update_from_marker(
    target_dataframe,
    worksheet,
    marker_column,
    value_columns
):

    clean_marker_column(
        target_dataframe,
        marker_column
    )

    clean_marker_column(
        worksheet,
        marker_column
    )

    worksheet = validate_marker_lookup(
        worksheet=worksheet,
        marker_column=marker_column,
        value_columns=value_columns
    )

    target_markers = set(
        target_dataframe[marker_column]
        .dropna()
        .unique()
    )

    worksheet_markers = set(
        worksheet[marker_column]
        .dropna()
        .unique()
    )

    missing_from_worksheet = sorted(
        target_markers - worksheet_markers
    )

    if missing_from_worksheet:
        raise ValueError(
            f"{len(missing_from_worksheet):,} {marker_column} "
            f"value(s) from studysample_withcuts were not found "
            f"in the edited worksheet: "
            f"{missing_from_worksheet}"
        )

    worksheet_lookup = (
        worksheet
        .set_index(marker_column)
    )

    for value_column in value_columns:

        target_dataframe[value_column] = (
            target_dataframe[marker_column]
            .map(worksheet_lookup[value_column])
        )

    return target_dataframe


#==============================================================================
# SEX
#==============================================================================

studysample_withcuts = update_from_marker(
    target_dataframe=studysample_withcuts,
    worksheet=sex_worksheet,
    marker_column='SEX_REVIEW_MARKER',
    value_columns=[
        'SEX'
    ]
)


#==============================================================================
# RACE
#==============================================================================

studysample_withcuts = update_from_marker(
    target_dataframe=studysample_withcuts,
    worksheet=race_worksheet,
    marker_column='RACE_REVIEW_MARKER',
    value_columns=[
        'RACE',
        'RACE_DESC'
    ]
)


#==============================================================================
# PROFICIENCY LEVEL
#
# PL_CODE and PL_DESC are taken directly from the edited worksheet.
# If either worksheet cell was cleared, the corresponding value in
# studysample_withcuts will become missing.
#==============================================================================

for col in ['REVIEWED_PL_CODE', 'REVIEWED_PL_DESC']:
    if col not in studysample_withcuts.columns:
        studysample_withcuts[col] = pd.NA


studysample_withcuts = update_from_marker(
    target_dataframe=studysample_withcuts,
    worksheet=pl_worksheet,
    marker_column='PL_REVIEW_MARKER',
    value_columns=[
        'REVIEWED_PL_CODE',
        'REVIEWED_PL_DESC'
    ]
)

# UPDATE PL_CODE AND PL_DESC with reviewed data
# original values prior to review are in the 
# columns 'CUTS_PROFICIENCY_LEVEL', 'CUTS_PROFICIENCY_NAME'
studysample_withcuts['PL_CODE'] = (
    studysample_withcuts['REVIEWED_PL_CODE']
)

studysample_withcuts['PL_DESC'] = (
    studysample_withcuts['REVIEWED_PL_DESC']
)


#==============================================================================
# ROW-COUNT QA
#==============================================================================

ending_row_count = len(studysample_withcuts)

if ending_row_count != starting_row_count:
    raise ValueError(
        f"Row count changed while applying worksheet edits. "
        f"Before: {starting_row_count:,}; "
        f"After: {ending_row_count:,}"
    )

print(
    f"Worksheet updates completed without changing row count: "
    f"{ending_row_count:,} rows"
)


#==============================================================================
# MARKER QA
#==============================================================================

marker_qa = pd.DataFrame(
    {
        'MARKER': [
            'SEX_REVIEW_MARKER',
            'RACE_REVIEW_MARKER',
            'PL_REVIEW_MARKER'
        ],
        'MISSING_MARKERS': [
            studysample_withcuts[
                'SEX_REVIEW_MARKER'
            ].isna().sum(),

            studysample_withcuts[
                'RACE_REVIEW_MARKER'
            ].isna().sum(),

            studysample_withcuts[
                'PL_REVIEW_MARKER'
            ].isna().sum()
        ],
        'UNIQUE_MARKERS': [
            studysample_withcuts[
                'SEX_REVIEW_MARKER'
            ].nunique(dropna=True),

            studysample_withcuts[
                'RACE_REVIEW_MARKER'
            ].nunique(dropna=True),

            studysample_withcuts[
                'PL_REVIEW_MARKER'
            ].nunique(dropna=True)
        ]
    }
)

print(marker_qa)


#==============================================================================
# UPDATED VALUE QA
#==============================================================================

qa_sex = (
    studysample_withcuts[
        [
            'SEX_REVIEW_MARKER',
            'SEX'
        ]
    ]
    .value_counts(dropna=False)
    .reset_index(name='COUNT')
    .sort_values(
        ['SEX_REVIEW_MARKER'],
        na_position='last'
    )
)

qa_race = (
    studysample_withcuts[
        [
            'RACE_REVIEW_MARKER',
            'RACE',
            'RACE_DESC'
        ]
    ]
    .value_counts(dropna=False)
    .reset_index(name='COUNT')
    .sort_values(
        ['RACE_REVIEW_MARKER'],
        na_position='last'
    )
)

qa_pl = (
    studysample_withcuts[
        [
            'PL_REVIEW_MARKER',
            'D_SUBJECT',
            'D_GRADE_CLEAN',
            'D_PLCODE',
            'D_PLDESC',
            'PL_CODE',
            'PL_DESC'
        ]
    ]
    .value_counts(dropna=False)
    .reset_index(name='COUNT')
    .sort_values(
        [
            'D_SUBJECT',
            'D_GRADE_CLEAN',
            'PL_REVIEW_MARKER'
        ],
        na_position='last'
    )
)

print(qa_sex)
print(qa_race)
print(qa_pl)



#==============================================================================
# QA
#==============================================================================
df = studysample_withcuts.copy()


# match-type counts
df[['MATCH_TYPE','MATCH_DESCRIPTION']].value_counts(dropna = False)

# PHASE5
looky_phase5 = df[df['MATCH_TYPE'] == 'PHASE_5']

# PHASE4
looky_phase4 = df[df['MATCH_TYPE'] == 'PHASE_4']


df[['PL_CODE', 'PL_DESC']].value_counts(dropna = False)


df['D_TERM'].value_counts(dropna = False)




#==============================================================================
# UPLOAD STUDYSAMPLE-- ADD BACK THE RECORDS THAT DON'T MERGE with no
#                     SS or SS_ADJ?
#                    they were dopped and in qa_dropped_records
#==============================================================================


#qa----------------------------
sample_mismatch = qa_dropped_from_cuts.loc[:,['MATCH_TYPE','MATCH_DESCRIPTION','D_DISTRICTNAME','D_STATE_STID','D_DOB',
                                          'M_GRADE_ORDINAL','D_GRADE','D_TESTNAME','D_SS', 'D_PLCODE', 'D_PLDESC']]

