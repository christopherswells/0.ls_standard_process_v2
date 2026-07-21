/*
 cleaning done prior for join fields.  need to document.
 eg. fname is uppder and trimmed.  state id numerical with
 nulls converted to -1 in map -99 in district so they wont merge.

*/


CREATE TABLE $STATE_ABR$DATA_YEAR_STUDYSAMPLE_QA AS
select 
 CASE
     WHEN M.STUDENT_STATE_ID = D_STATE_STID
         THEN 'STATE_STID'
     WHEN (D_LOCAL_STID = M.STUDENT_ID
         AND D_AGENCYCODE = M.DISTRICT_AGENCY_CODE
         )
         THEN 'LOCAL'
     WHEN( D_LNAME= M.STUDENT_LAST_NAME
         AND D_FNAME = M.STUDENT_FIRST_NAME
         AND D_DOB_ASDATE = M.R_DOB
         )
         THEN 'FUZZY'
           ELSE 'UNMATCHED'
     END AS MATCH_TYPE
     ,M.STUDENT_BUSINESS_IDENTIFIER
     ,D_GRADE
     ,M.GRADE_ORDINAL AS M_GRADE
     ,CASE (M.STUDENT_STATE_ID)
       when -1 then NULL
       else M.STUDENT_STATE_ID
       END AS M_STATE_STID
     ,case (D_STATE_STID)
         when -99 then NULL
      else D_STATE_STID 
      END as D_STATE_STID     
     ,case(M.STUDENT_ID )
       when -1 then NULL
       else M.STUDENT_ID     
      END AS M_LOCAL_STID
     ,case (D_LOCAL_STID)
         when -99 then NULL
      else D_LOCAL_STID 
      END as D_LOCAL_STID
     ,D_SUBJECT
     ,D_SUBJECT_CODE
     ,M.SUBJECT AS M_SUBJECT
     ,M.MEASUREMENT_SCALE_BID
     ,M.TEST_NAME
     ,M.TEST_KEY
     ,M.TESTDATE AS M_TESTDATE
     ,D_MAPGROWTH_TEST_NAME
     ,M.STUDENT_LAST_NAME
     ,D_LNAME
     ,M.STUDENT_FIRST_NAME
     ,D_FNAME
     ,M.R_DOB
     ,D_DOB
     ,D_DISTRICTNAME
     ,M.DISTRICT_STANDARD_NAME
     ,D_FILENAMEFROMDISTRICT
     ,D_AGENCYCODE
     ,M.DISTRICT_AGENCY_CODE AS M_AGENCYCODE
     ,M.DISTRICT_BUSINESS_IDENTIFIER
     ,M.DISTRICT_STANDARD_NAME AS M_DISTRICTNAME
     ,'$STATE_ABR' AS STATE
     ,D_TERM AS TERM
     ,M.SCHOOL_BUSINESS_IDENTIFIER
     ,M.SCHOOL_STANDARD_NAME AS SCHOOLNAME
     ,D.D_SCHOOLNAME
     ,M.STUDENT_GENDER AS M_SEX
     ,D_SEX
     ,COALESCE(CASE WHEN upper(D_SEX) in ('M','MALE','1') THEN 1
                    WHEN UPPER(D_SEX) in ('F','FEMALE','0') THEN 0
                    ELSE NULL
                   END ,
               CASE WHEN upper(M.STUDENT_GENDER) in ('M','MALE','1') THEN 1
                    WHEN UPPER(M.STUDENT_GENDER) in ('F','FEMALE','0') THEN 0
                    ELSE NULL
                   END) AS SEX
     ,D_ETHNICITY
     ,D_RACE
     ,M.NWEA_ETHNIC_GROUP_NAME
     ,M.IRIT
     ,M.SEM
     ,D_SS
     ,'' AS SS_ADJ
     ,D_PL
     ,'' AS D_DUMMYID     
     ,D.D_TESTDATE
     ,D.D_SPED
     ,D.D_ELL
     ,D.D_IEP
     ,D.D_SEC504
     ,D.D_FRL

     ,D.D_RETEST
     ,TEST_GRADE_LOW
     ,TEST_GRADE_HIGH

FROM LINKING_STUDIES.$STATE_ABR$DATA_YEAR_LINKINGSTUDY_PARTNERDATA AS D
         INNER JOIN LINKING_STUDIES.$STATE_ABR$DATA_YEAR_MAPDATA AS M
                   on M.TEST_NAME = D_MAPGROWTH_TEST_NAME
                   and M.STUDENT_STATE_ID = D_STATE_STID
                       OR (
                                    M.TEST_NAME = D_MAPGROWTH_TEST_NAME
                                AND D_AGENCYCODE = M.DISTRICT_AGENCY_CODE                                                             
                                AND D_LOCAL_STID = M.STUDENT_ID
                                
                            )
                       OR (         M.TEST_NAME = D_MAPGROWTH_TEST_NAME
                                AND D_AGENCYCODE = M.DISTRICT_AGENCY_CODE
                                AND D_LNAME = M.STUDENT_LAST_NAME
                                AND D_FNAME = M.STUDENT_FIRST_NAME
                                AND D_DOB_ASDATE = M.R_DOB                             
                            )
                                                
                                            
        order by M.STUDENT_BUSINESS_IDENTIFIER
;
