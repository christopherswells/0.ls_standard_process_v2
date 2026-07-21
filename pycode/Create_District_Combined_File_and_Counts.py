# -*- coding: utf-8 -*-
"""
Created on Wed Jul 30 12:58:08 2025

@author: Chris.Wells
"""
'''
4/25/2023

@author: Chris.Wells

Gets counts of students per district for linking studies 

RUN PARTNER COUNTS FOR NY 2024 EOG
S:\MAPGrowth\Linking\Data Files\2024\--


see Trello for TODO:  https://trello.com/c/PflYXtlY/16-linking-study-counts-code-in-sql-and-in-py


1. Create new line above column names in combined file found in project folder
2. add new line of abbreviated column names in row 1. 
   (see P:\Team\ChrisWells\MAPRF\MRF GIT\State Linking Study\Linking Study Partner Counts\GENERIC_dist_combined.xlsx)
3. Enter datapath, and combinedfile name in settings below
4. BELOW in settings, enter graderange for ss fields (eg. 'sci_ss' :   ['6','7','8']  )
    use quoted grades entered individually as list. an empty list, eg. 'biol_ss': [] will
    accept any grade as valid for the given test.
5. run program.  If any district files have improper form, the program will stop 
   and a list of district files to check will be given.  causes of errors in structure
   are often:
       * data file is not first tab
       * columns are either added or omitted from the file
       
       
out files will be placed in a folder called 'Output' within the datapath provided in settings (also found in Trello)


CHANGES:
        * output for combined file and removedRecords going to csv instead of xlsx.
            -code for both remains below.
        * add timestamp to output

'''



#%%

#==============================================================================
# below is copy from ny2024 getdistrictcunts
#==============================================================================


import pandas as pd
import glob  #to read all excel files in directory
import re   
import os
from datetime import datetime
import sys
import numpy as np
from pathlib import Path



# IN SPYDER THE WORKING DIR IS NOT ALWAYS SETTING TO THE PROJECT DIR.  HARDCODED THE PROJECT DIR LOCATION.
os.chdir(r'K:\SMS Team\Chris_Wells\3.Linking\0. Standard Process\Linking_Studies_Data_Prep_code')
sys.path.append(r'K:\SMS Team\Chris_Wells\3.Linking\0. Standard Process\Linking_Studies_Data_Prep_code')

# CHECK IF THE CWD --> ...\Linking_Studies_Data_Prep_code
if os.path.basename(os.getcwd())  != 'Linking_Studies_Data_Prep_code':
    print('Your Working directory is : ' + os.getcwd())
    print('Your Working directory should be the location of this folder: "Linking_Studies_Data_Prep_code"')
    
from py.settings import *




combo = os.path.join(DATA_ROOT ,DATA_TEMPLATE) #district combined file. not sure if needed here now.
combinedDF = pd.read_excel(combo, nrows = 0) #set up combinedDF - use structure from combined file?

# COMING FROM SETTINGS NOW
# subject = SUBJECTNAMES



# #Create output directory if not exists
# outPath = datapath + '\\Output'
# if not os.path.exists(outPath):
  
#    os.makedirs(outPath)
#    print("The Output directory was created: " + str(outPath))
   
   


####   OUT TO XLSX ###
outRemovedRecords = os.path.join(outPath, 'Output_RemovedRecords.xlsx' )
outCombinedDF = os.path.join(outPath,'Output_' + outCombinedFile + '.xlsx' )
outDistrictCounts = os.path.join(outPath,'Output_DistrictCounts.xlsx')
out_testCountsByGrade = os.path.join(outPath,'Output_TestCountsByGrade.xlsx')




#==============================================================================
# GET COMBINED FILE STRUCTURE AND LIST OF FILES TO IMPORT
#==============================================================================

#SET UP 
#districtsIn = pd.DataFrame()  #DF of district files as read in, concatenated
tempDF = pd.DataFrame()  #temp to hold one district as reading in 
manualReadDistricts = []    #Districts that will need a human to look at before import
droppedRecordsCombined = pd.DataFrame() #dataframe of all dropped records with column indicating reason.
                                        #Can be corrected in Excel and rerun.

# PERMANENT SETTINGS ----------------------------------------------------------
digitsPattern = re.compile(r'\d+') #the district code is in filename immediately prior to '.xlsx'-- not working going to use split instead


# DEFINE CUSTOM ERRORS FOR DISTRICT FILES-------------------------------------
class FileStructureError (Exception):
    pass

class agencyCodeError (Exception):
    pass


#TODO: ADD TRY...  THE COMBO SHOULD GIVE BETTER ERROR INFO IF '.XLSX' 
# MISSING OR UNEXPECTED FILENNAME FOR COMBINED/TEMPLATE


# READ XLSX FILES IN PATH except combined file---------------------------------
filenames = glob.glob(datapath + "\*.xlsx")

#READ EITHER XLSX OR CSV PARTNER FILES-----------------------------------------
# filenames = []
# for ext in ("*.xlsx", "*.csv"):
#     filenames.extend(glob.glob(os.path.join(datapath, ext)))

# HAVEN'T SWITCHED TO PATH YET
# datapath = Path(datapath)  # ensure it's a Path object
# patterns = ("*.xlsx", "*.csv")
# filenames = [p for pat in patterns for p in datapath.glob(pat) if not p.name.startswith("~$")]




# Columns read in from combined file
combinedDFColsIn = combinedDF.columns.tolist() #to check that the number of columns of district files match prior to changes to combinedDF structure


 #DF of records that are weeded out
removedRecords = pd.DataFrame(columns = ['reasonForRemoval'] + combinedDF.columns.tolist())

#Add filename from district (Trello file) to combinedDF 
combinedDF['filenameFromDistrict'] = ''     #will contain filename from district input file (see Trello)

print(combinedDF.columns)


#==============================================================================
# FUNCTION DEFINITIONS
#==============================================================================

def check_file_structure(districtCols, combinedCols):         
        
    if len(districtCols) != len(combinedCols): 
        raise FileStructureError() 
        print('district column count = ' + str(len(districtCols)) + '     combined column count = ' + str(len(combinedCols)))
        #GET EXCEL SHEET NAME
    return 


def addRejectionReason(df, reason):
    #add the reason to first column of rejected records for concatenation to rejectedRecords DF    
    df.insert(loc = 0, column = 'reasonForRemoval', value = reason)
    return df


def check_dob(DF):
    #   NOT IN USE AS OF 11/5/2024.  BAD DOB WILL DROP OUT IN MERGE IF DOB NEEDED.  IRRELEVANT IF IDS MATCH STUDENTS.
    
    #creates new temp col for converted datetimes.  
    #writes screwy dob to screwy file (ones that can't be converted to timestamp/datetime) with DOB as reason for removal.
    #records with dob that can be read as timestamp/datetime are formated as '%m-%d-%Y'       
   
    DF['dobDatetime'] = pd.to_datetime(DF['dob'], errors = 'coerce')   # Will be Nat if can't convert to date

    #records that were successfully converted to dates.  replace string dob with date.
    # goodDOB =  DF.loc[DF['dobDatetime'].notna()].copy()
    goodDOB = DF.copy()             #NOT GOING TO REMOVE MISSING DOB ANYMORE thus dropping line above.
    goodDOB['dob'] = goodDOB['dobDatetime'].dt.strftime('%m-%d-%Y')
    goodDOB.drop(columns = 'dobDatetime', inplace = True)
    
    
    # NOT GOING TO REMOVE FOR BAD DOB.  
    # THEY CAN MERGE ON IDS OR SIMPLY FALL OUT AT MERGE IF DOB NEEDED
    # records that failed to convert to dates. Keep the string dob for analyst review.    
    screwyDOB =  DF.loc[DF['dobDatetime'].isna()].copy()    
    screwyDOB.drop(columns = 'dobDatetime', inplace = True)
    screwyDOB = addRejectionReason(screwyDOB, 'removed_DOB')   
    
    return goodDOB, screwyDOB
    
  

#TODO: If ANY of the tests has a score with valid gradeWhenTested, the record will be kept with all scores.  Is this correct?
#TODO: Currently the record is kept in both in good record file and in bad record file.


def check_gradeRange(DF):

    goodGradeRange = pd.DataFrame(columns=DF.columns)
    screwyGradeRange = pd.DataFrame(columns=DF.columns)
    tempGoodGradeRange = pd.DataFrame(columns=DF.columns)
    tempScrewyGradeRange = pd.DataFrame(columns=DF.columns)

    for testSS in gradeRange.keys():  

        if len(gradeRange.get(testSS)) == 0:    
            tempGoodGradeRange = DF.loc[DF[testSS].notnull()].copy()

        else:    
            DF['input_grade'] = DF['grade']
            DF['numericalGrade'] = pd.to_numeric(DF['grade'], errors='coerce')

            tempGoodGradeRange = DF.loc[
                (DF[testSS].notnull()) & 
                (DF['numericalGrade'].isin(gradeRange.get(testSS)))
            ].copy()

            tempScrewyGradeRange = DF.loc[
                (DF[testSS].notnull()) & 
                (~DF['numericalGrade'].isin(gradeRange.get(testSS)))
            ].copy()

            tempGoodGradeRange.loc[:, 'grade'] = tempGoodGradeRange['numericalGrade']
            tempScrewyGradeRange.loc[:, 'grade'] = tempScrewyGradeRange['input_grade']

            tempGoodGradeRange = tempGoodGradeRange.drop(columns=['numericalGrade','input_grade'])
            tempScrewyGradeRange = tempScrewyGradeRange.drop(columns=['numericalGrade','input_grade'])

            DF.drop(columns=['numericalGrade','input_grade'], inplace=True)

        if not tempGoodGradeRange.empty:
            goodGradeRange = pd.concat([goodGradeRange, tempGoodGradeRange])
        if not tempScrewyGradeRange.empty:
            screwyGradeRange = pd.concat([screwyGradeRange, tempScrewyGradeRange])

    goodGradeRange.drop_duplicates(inplace=True)

    screwyGradeRange2 = pd.merge(
        screwyGradeRange, 
        goodGradeRange[['state_stid']], 
        on='state_stid', 
        how='outer', 
        indicator=True
    )
    screwyGradeRange2 = screwyGradeRange2.loc[screwyGradeRange2['_merge']=='left_only']
    screwyGradeRange2 = addRejectionReason(screwyGradeRange2, 'removed_gradeRange')
    screwyGradeRange2.drop_duplicates(inplace=True)
    screwyGradeRange2.drop(columns='_merge', inplace=True)

    return goodGradeRange, screwyGradeRange2




def check_scores_exist(DF):
    #convert scale scores to Int64 or null
    #Check across scores that at least one Int64, non-null scale score exists    
    
    goodScores = pd.DataFrame()
    screwyScores = pd.DataFrame()    

    #convert to numerical.  non-numerical --> null.  
    #'goodScores' dataframe is created from the converteed-to-int-or-null DF
    #'screwyScores' uses the original DF to view what was originally in score
    goodScores = DF.copy()
    for score in gradeRange.keys():
        goodScores[score] = pd.to_numeric(goodScores[score], errors = 'coerce').astype('Int64')      
    goodScores = goodScores[~goodScores[gradeRange.keys()].isna().all(axis = 1)]
    
    # screwyScores = DF[DF[gradeRange.keys()].isna().all(axis = 1)]    
    screwyScores = DF[~DF.index.isin(goodScores.index)]
    screwyScores2 = addRejectionReason(screwyScores, 'removed_noScores')     
    return goodScores, screwyScores2

def check_Lname_exist(DF):
    #Check across scores that at least one non-null exists 
    
    goodLname = pd.DataFrame()
    screwyLname = pd.DataFrame()          
    goodLname = DF[~DF['lname'].isna()]
    screwyLname = DF[DF['lname'].isna()]  
    screwyLname2 = addRejectionReason(screwyLname, 'removed_Lname')     
    return goodLname, screwyLname2

def check_Fname_exist(DF):
    #Check across scores that at least one non-null exists 
    
    goodFname = pd.DataFrame()
    screwyFname = pd.DataFrame()          
    goodFname = DF[~DF['fname'].isna()]
    screwyFname = DF[DF['fname'].isna()]  
    screwyFname2 = addRejectionReason(screwyFname, 'removed_Fname')     
    return goodFname, screwyFname2

def fixGender(DF):
    #turn 'Female', female','Male','male' into 'F','M' accordingly
    
    DF['sex'] = np.where(DF['sex'].isin(['Female','female']), 'F', DF['sex'])
    DF['sex'] = np.where(DF['sex'].isin(['Male','male']), 'M', DF['sex'])
    return DF



def get_filenameNoPath(fileWithPath):       
    #remove path from filename    
    return fileWithPath.split('\\')[-1]


def get_district_code_from_filename(DF, filename):
    #assumes district code is a number immediately prior to 'xlsx' in filename
    #eg.newman's code is 17245 -- Newman International Academy of Arlington 17245.xlsx
    filenameNoPath =  get_filenameNoPath(filename)
    numbersInFilename = digitsPattern.findall(filenameNoPath)
    districtCode  = numbersInFilename[len(numbersInFilename) - 1]
    
    DF[combinedDF.columns.tolist()[0]] = districtCode #first column is 'State' which will be replaced with the district code 
    DF['filenameFromDistrict'] = filenameNoPath  #Add filename from District file for sorting to match Trello card district order
    return DF

# def remove_and_dont_count_noIDs(DF):
#     '''
#     DF = district data frame
#     returns DF
#     removes but doesn't count as removed records that have no name or IDs. 
#     This will remove extra extra rows at bottom of sheet
#     '''
#     DF = DF.loc[]

  

# def check_mergeFields(DF):
    
#     return goodMergeFields, screwyMergeFields


#%%  
    
            
#=================================================================================== 
# RUNNING PART 1: pre-checks-- check errant files for missing columns, wrong tabs etc.
#                 before continuing to part 2 checks.
#===================================================================================                
#  check_file_structure(tempDistrictDF, combinedDF)                
#  tempDistrictDF = pd.read_excel(file, names = combinedDF.columns.tolist() ) #read in full file              
#  tempDistrictDF = get_district_code_from_filename(tempDistrictDF, file)              
                
#check that filename has agency code prior to '.xlsx' and correct number of columns
for file in filenames:
    print()
    print('reading file:  ' + file)
    
    
    # tempDistrictDF = pd.read_excel(file, nrows = 0) #to check file structure
    
    # does this fix the locking issue that sometimes happens when 
    # manualreaddistrict flagged after using pd.read_excel?
    with pd.ExcelFile(file, engine="openpyxl") as xls:
        tempDistrictDF = pd.read_excel(xls, nrows=0)

           
    try:
        # print('try col check')
        #Any QC that if fails indicates test must be manually read and fixed
        tempFileCols = tempDistrictDF.columns.tolist()   #may use for deeper checks later        
        check_file_structure(tempFileCols, combinedDFColsIn)   
           
    except FileStructureError:
        
        print()
        print('--file structure error: ' + get_filenameNoPath(file))
        
        #ADD ERROR TYPE TO DF?
        manualReadDistricts.append(file)      
    
        
    try:    
        # print('in Agency code check')
        tempDistrictDF = get_district_code_from_filename(tempDistrictDF, file)
    except (NameError, IndexError):
        print('--District Code Error:  ' + get_filenameNoPath(file))
        manualReadDistricts.append(file) 
     

#----------------------------------------------
# SOME FILES COULD NOT BE READ IN
# Indicate error for some districts
#----------------------------------------------

if len(manualReadDistricts) != 0:
    print()
    print("These districts don't match the DATA TEMPLATE:")
    print("\n".join(map(str, manualReadDistricts)))
    print()
    # Prefer this in notebooks/VS Code Interactive:
    raise RuntimeError("Some files require manual read. See the list above.")
      
     


#=================================================================================== 
# Run Checks for validity rules  on Districts that could be read in
#===================================================================================  
if len(manualReadDistricts) == 0:
    for file in filenames:
        try:   
            print('reading file: ' + get_filenameNoPath(file))        
            tempDistrictDF = pd.read_excel(file, 
                                           names = combinedDFColsIn,
                                           dtype= {'grade':str, 'dob':str}
                                           ) #read in full file, Grade is str in case of 'K'
            
        except:
            print()
            print('--Trouble reading in file: ' + get_filenameNoPath(file))
            
        else:
            
            #Hidden rows, etc. sometimes have no IDs or lastname.  delete but dont count as 'removed' record.
            # tempDistrictDF= remove_and_dont_count_noIDs(tempDistrictDF)
            
            #Run each check per district.  keep records that pass checks in tempDistrictDF and failed records in removed...
            
            #CLEANING FUNCTIONS ONLY-- NO REMOVAL OF RECORDS
                        
            
            
            #FUNCTIONS THAT MAY REMOVE IMPCOMPLETE RECORDS            
            tempDistrictDF = get_district_code_from_filename(tempDistrictDF, file) #replace State with agency code.  There was already a check on the district codes?
#             tempDistrictDF, removedDOB = check_dob(tempDistrictDF) #GET DOB problem records
            tempDistrictDF, removedNoScores = check_scores_exist(tempDistrictDF)
            tempDistrictDF, removedGradeRange = check_gradeRange(tempDistrictDF) #remove records unless at least one test has valid score and grade in range
#             tempDistrictDF, removedLname = check_Lname_exist(tempDistrictDF)
#             tempDistrictDF, removedFname = check_Fname_exist(tempDistrictDF)
            # tempDistrictDF = fixGender(tempDistrictDF)
            
            
            #concat all accepted records       
            combinedDF = pd.concat([combinedDF,tempDistrictDF], axis=0, ignore_index = True)  #Do this for only passing files.  Anything to open manually don't add.
            
            #Concat all removed records
            # removedRecords = pd.concat([removedRecords , removedDOB ]) # see above.  not removing for DOB.
            removedRecords = pd.concat([removedRecords , removedNoScores ])
            removedRecords = pd.concat([removedRecords , removedGradeRange ])  
#             removedRecords = pd.concat([removedRecords , removedLname ])
#             removedRecords = pd.concat([removedRecords , removedFname ])
 


      
#%%

#=================================================================================== 
# OUTPUT 
#===================================================================================  
 

#========== PREP OUTPUT FILES =======##  
            
#get distinct agencycode to 'filenameFromDistrict' to help sort order
keptDistricts = combinedDF[['agencycode','filenameFromDistrict']].drop_duplicates()
removedDistricts = removedRecords[['agencycode','filenameFromDistrict']].drop_duplicates()
allDistricts = pd.concat([keptDistricts, removedDistricts]).drop_duplicates().sort_values('agencycode')

#counts by agencycode-- might be useful to output with districtname, but districtname-agencycode is not 1-to-1.
districtFinalCounts = combinedDF['agencycode'].value_counts().rename_axis('agencycode').reset_index(name = 'final_counts')
districtRemovedCounts = removedRecords.groupby(['agencycode','reasonForRemoval'])['agencycode'].count().reset_index(name = 'removed_count')


#==== MAKE DISTRICT LEVEL OUTPUT OF COUNTS AND COUNTS REMOVED- ONE RECORD PER DISTRICT
districtRemovedCountsWide = districtRemovedCounts.pivot(index = ['agencycode'], columns = 'reasonForRemoval', values = 'removed_count' )

#District Counts
districtCounts = pd.merge(allDistricts, districtFinalCounts, on = 'agencycode', how = 'left')
districtCounts = pd.merge(districtCounts, districtRemovedCountsWide ,  on = 'agencycode', how = 'left')
districtCounts = districtCounts.drop_duplicates().sort_values('filenameFromDistrict') 

#agencySummary = '('
#for each record, if colname is not nan, agencySummary += str(colname) + ' n = ' + cellvcalue


# ADD TO OUTPUT- 5/10/2024
# create counts of tests according to number of tests with ss scores (eg. ela_ss)
# testCountsByGrade = combinedDF.groupby('grade')[subjects].count()
testCountsByGrade = combinedDF.groupby('grade')[subjects].count()


#=================================================================================== 
# OUTPUT
#===================================================================================  
 
#TODO: Drop filename from removed and combined
removedRecords.to_excel(outRemovedRecords, index = False)
combinedDF.to_excel(outCombinedDF, index = False)
districtCounts.to_excel(outDistrictCounts, index = False)

# to Excel
districtCounts.to_excel(outDistrictCounts, index = False)
removedRecords.to_excel(outRemovedRecords, index = False)
combinedDF.to_excel(outCombinedDF, index = False)

# ADD TO OUTPUT- 5/10/2024
testCountsByGrade.to_excel(out_testCountsByGrade, index = True)





