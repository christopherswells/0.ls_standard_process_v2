# -*- coding: utf-8 -*-
"""
Created on Wed Jun 10 05:45:25 2026

@author: Chris.Wells


Export college readiness scores to be ingested by college readiness code

The scores have not been removed from this data, but will not be processed
as part of the WI study.
"""

import pandas as pd
from pycode.settings import *


df_wide = pd.read_parquet(DATA_ROOT / "df_wide.parquet")

cr_data = df_wide.drop(columns = ['ELA_TESTNAME', 'ELA_SS', 'ELA_PLDESC', 'ELA_PLCODE',
                        'ELA_TESTDATE', 'MATH_TESTNAME', 'MATH_SS', 'MATH_PLDESC',
                        'MATH_PLCODE', 'MATH_TESTDATE'])

# college readiness data where the Scale Scores are not missing (incl whitespace)
cr_out = cr_data.loc[
    cr_data["ACT_READING_SS"].replace(r"^\s*$", pd.NA, regex=True).notna() |
    cr_data["ACT_MATH_SS"].replace(r"^\s*$", pd.NA, regex=True).notna()
]


outdir = r'S:\MAPGrowth\Linking\Data Files\2026\College Readiness Study\edited_files'
filename = 'WI - college readiness from WI data collection.xlsx'

outfile = outdir + '\\' + filename

cr_out.to_excel(outfile, index = False)