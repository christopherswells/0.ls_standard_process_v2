/*

EOG_Counts_By_Grade.sql

*/

select distinct DISTRICT_GEOGRAPHY_NAME,
                TERM_NAME,  
                SUBJECT, 
                MEASUREMENT_SCALE_BID,  
                TEST_NAME, 
                GRADE_ORDINAL as GRADE,                
                count(distinct SCHOOL_STANDARD_NAME) as school_count,
                count(distinct STUDENT_BUSINESS_IDENTIFIER) as student_count
        FROM RESEARCH_DATA.MAP_GROWTH_TEST_EVENT_NORMS_LINKING_STUDY_VW
where TERM_NUMBER = '$TERM_NUMBER'
  AND DISTRICT_GEOGRAPHY_NAME = '$STATE_NAME'   
   and assess_score is not null
  /* and grade >= '$MIN_GRADE'
   AND grade <= '$MAX_GRADE'*/
   /*and grade_ordinal between TEST_GRADE_LOW and TEST_GRADE_HIGH*/
   and TEST_NAME IN ( $TESTNAMES )
group by DISTRICT_GEOGRAPHY_NAME, TERM_NAME, subject, MEASUREMENT_SCALE_BID, TEST_NAME, GRADE_ORDINAL
order by MEASUREMENT_SCALE_BID, TEST_NAME, GRADE;



