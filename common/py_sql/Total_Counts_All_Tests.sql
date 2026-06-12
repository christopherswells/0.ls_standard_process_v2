/*
Created on Thu Jun 26 18:25:59 2025

@author: Chris.Wells

total_testCounts_by_subject_code.sql

GET ALL TESTNAMES AND COUNTS FOR TESTS IN GIVEN SUBJECT CODES

*/


SELECT        DISTRICT_GEOGRAPHY_NAME,
              TERM_NAME,  
               SUBJECT, 
               MEASUREMENT_SCALE_BID,  
               TEST_NAME,
               count(*)
FROM RESEARCH_DATA.MAP_GROWTH_TEST_EVENT_NORMS_LINKING_STUDY_VW
WHERE TERM_NUMBER = '$TERM_NUMBER'
AND DISTRICT_GEOGRAPHY_NAME = '$STATE_NAME'

/*and TEST_NAME LIKE ANY ('%Algebra%','%Geometry%', '%Reading%', '%Math%')*/

AND MEASUREMENT_SCALE_BID IN $SUBJECT_STR

and GROWTH_EVENT_YN = 1
group by  DISTRICT_GEOGRAPHY_NAME,
              TERM_NAME,  
               SUBJECT, 
               MEASUREMENT_SCALE_BID,
               TEST_NAME,
                MEASUREMENT_SCALE_BID
order by  MEASUREMENT_SCALE_BID,  count(*) desc;

