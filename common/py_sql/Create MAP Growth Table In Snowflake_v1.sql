/*
    Create  MAP DATA TABLE
    
    USE ROLE RESEARCH_PRD_MAPGROWTH_PSYCHOMETRIC_SOLUTIONS_FR;
    USE WAREHOUSE RESEARCH_PRD_MAPGROWTH_PSYCHOMETRIC_SOLUTIONS_WH;
    USE DATABASE RESEARCH_PRD_GRD_DB;


    SET TERM_NUMBER = 202402;  --varchar in MAP.  see linking study planning form for MAP term to use.
    SET STATE_CODE = 'MD';    --code to be used in output
    SET STATE_NAME = 'MARYLAND'; --state name as exists in MAP testevent view



 */

create or replace table $STATE_ABR$DATA_YEAR_MAPDATA  as
select '$STATE_ABR' as STATE
              , m.district_business_identifier
              , m.DISTRICT_STANDARD_NAME   --added 10/9 in NY for QA
              , m.DISTRICT_AGENCY_CODE  --added 10/9 in NY since we dont have agency code provided by partner
              , m.school_business_identifier
              , m.SCHOOL_STANDARD_NAME --added 10/9 in NY for QA
              , m.grade_ordinal
              , m.student_business_identifier -- replaces grd_key
              , m.nwea_ethnic_group_name
              , case('m.nwea_ethnic_group_name')
                  when 'American Indian or Alaska Native' then 1
                  when 'Asian' then 2
                  when 'Black or African American' then 3
                  when 'Hispanic or Latino' then 4
                  when 'Multi-ethnic' then 5
                  when 'Native Hawaiian or Other Pacific Islander' then 6
                  when 'Not Specified or Other' then 7
                  when 'White' then 8
                 end             
               as nwea_ethnic_group_code
              , m.ASSESS_SCORE::INT  as IRIT 
              , m.ASSESS_STD_ERR::DECIMAL (5,2) AS SEM 
              , m.test_name
              , m.test_key -- replace assess_grd_key
              , m.student_gender
              , upper(trim(m.student_first_name)) as student_first_name
              , upper(trim(m.student_last_name)) as student_last_name
              
            --these will convert to -1 if non numerical.  partner data to -99.
              , nvl(try_to_number(m.student_state_id), -1) as student_state_id
              , nvl(try_to_number(m.student_id), -1) as student_id

              , CASE (m.measurement_scale_bid)
                    WHEN 12 THEN 7 -- SNOWFLAKE RECORDS SPANISH-DELIVERED READING TEST (LANGUAGE ARTS?) ARE ODED 0 NOT 7 PER LINKING DOCS SPECS.
                    ELSE m.measurement_scale_bid
                END AS measurement_scale_bid
              , m.measurement_scale_bid as measurement_scale_bid_snowflake

              , m.subject
              , m.TERM_NUMBER
              , m.test_grade_low
              , m.test_grade_high
              , m.assess_test_end_dt as testdate
              , m.LANGUAGE_ID -- added 1/29/25 to look at language before limiting output
              ,roster.date_of_birth as r_dob 
              ,m.DOB_YYYY_MM
              ,ROW_NUMBER() OVER (PARTITION BY  m.student_business_identifier,  m.TERM_NUMBER,  m.MEASUREMENT_SCALE_BID
                 ORDER BY  m.ASSESS_SCORE DESC) AS ROW_NUMBER --HIGHEST SCORE PER TERM/SUBJECT
            --FROM RESEARCH_DATA.MAP_GROWTH_TEST_EVENT_VW m
FROM RESEARCH_PRD_GRD_DB.RESEARCH_DATA.MAP_GROWTH_TEST_EVENT_NORMS_LINKING_STUDY_VW m

         LEFT JOIN ( SELECT DISTINCT student_business_identifier, term_number, date_of_birth from RESEARCH_DATA.MAP_STUDENT_ROSTER_NORMS_LINKING_STUDY_VW ) AS roster
                   on m.student_business_identifier = roster.student_business_identifier
                       and m.term_number = roster.term_number

where m.TERM_NUMBER = $TERM_NUMBER
  AND m.DISTRICT_GEOGRAPHY_NAME = '$STATE_NAME'
  AND m.valid_event_yn = 1   -- valid map test
  and m.assess_score is not null
  and TEST_NAME IN ( $TESTNAMES )
  
;
