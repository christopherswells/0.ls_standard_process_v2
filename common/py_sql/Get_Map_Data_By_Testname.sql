/*
    Create  MAP DATA TABLE

 */

create or replace table LINKING_STUDIES.MD2024_MAPDATA  as
select distinct $STATE_CODE as STATE
              , m.district_business_identifier
              , m.DISTRICT_STANDARD_NAME   --added 10/9 in NY for QA
              , m.DISTRICT_AGENCY_CODE  --added 10/9 in NY since we dont have agency code provided by partner
              , m.school_business_identifier
              , m.SCHOOL_STANDARD_NAME --added 10/9 in NY for QA
              , m.grade_ordinal
              , m.student_business_identifier -- replaces grd_key
              , m.nwea_ethnic_group_name
              -- ,'' as nwea_race_mapped_to_state_code --not sure what this should be

              , ASSESS_SCORE  -- CONVERTS TO INT IN MERGE
              , ASSESS_STD_ERR --DECIMAL(5,2) IN MERGE
              , m.test_name
              , m.test_key -- replace assess_grd_key
              , m.student_gender
              , m.student_first_name
              , m.student_last_name
              , m.student_state_id
              , m.student_id

              , CASE (m.measurement_scale_bid)
                    WHEN 12 THEN 7 -- SNOWFLAKE RECORDS SPANISH-DELIVERED READING TEST (LANGUAGE ARTS?) ARE CODED 12 NOT 7 PER LINKING DOCS SPECS.
                    ELSE m.measurement_scale_bid
        END AS measurement_scale_bid
              , m.measurement_scale_bid as measurement_scale_bid_snowflake

              , m.subject
              , m.TERM_NUMBER
              , m.test_grade_low
              , m.test_grade_high
              , m.assess_test_end_dt as testdate
              , m.LANGUAGE_ID -- added 1/29/25 to look at language before limiting output
              ,TRY_TO_DATE(roster.date_of_birth) as r_dob --Testevent dob doesnt have full date.  just month and year.
              ,m.DOB_YYYY_MM
              ,ROW_NUMBER() OVER (PARTITION BY  m.student_business_identifier,  m.TERM_NUMBER,  m.MEASUREMENT_SCALE_BID
                 ORDER BY  m.ASSESS_SCORE DESC) AS ROW_NUMBER --HIGHEST SCORE PER TERM/SUBJECT
            --FROM RESEARCH_DATA.MAP_GROWTH_TEST_EVENT_VW m
FROM RESEARCH_PRD_GRD_DB.RESEARCH_DATA.MAP_GROWTH_TEST_EVENT_NORMS_LINKING_STUDY_VW m

         LEFT JOIN ( SELECT DISTINCT student_business_identifier, term_number, date_of_birth from RESEARCH_DATA.MAP_STUDENT_ROSTER_NORMS_LINKING_STUDY_VW ) AS roster
                   on m.student_business_identifier = roster.student_business_identifier
                       and m.term_number = roster.term_number

where m.TERM_NUMBER = '$TERM_NUMBER'
  AND m.DISTRICT_GEOGRAPHY_NAME = '$STATE_NAME'

  AND m.valid_event_yn = 1   -- valid map test
  and m.assess_score is not null
  and TEST_NAME in ('$TESTNAMES')
  and GRADE_ORDINAL between TEST_GRADE_LOW and TEST_GRADE_HIGH
;
