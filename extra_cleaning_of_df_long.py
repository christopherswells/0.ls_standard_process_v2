# -*- coding: utf-8 -*-
"""
Created on Thu Aug 27 15:00:46 2026

@author: Chris.Wells


adhoc qa code while building TX

"""


#-------------------------------------------------
# TSIA Essay.  checking Scores.
# maybe same for diagnostic and/or other TSIA
# will clean scores downstream
#-------------------------------------------------

df_long.SUBJECT.value_counts()



essay = (
    df_long.loc[df_long['SUBJECT'] == 'TSIA2ESSAY', ['SS', 'PLCODE', 'PLDESC']]
    .value_counts(dropna=False)
)



#-------------------------------------------------
# Spanish Looky
#-------------------------------------------------

df_wide[['SUBJECT','GRADE']].value_counts(dropna = False)