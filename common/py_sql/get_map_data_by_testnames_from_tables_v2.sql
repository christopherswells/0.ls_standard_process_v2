
--set TABLE_NAME = $STATE_ABR || $STUDY_YEAR || '_MAPDATA';


create or replace table identifier('$MAP_TABLE_NAME') as
--create or replace table IDENTIFIER($map_table_name) as 

with included_districts as (

    select
        organization.district_geography_name_abbreviated as state,
        organization.organization_bid as district_business_identifier,
        organization.custom_name as district_standard_name,
        organization.partner_id as partner_id,
        organization.district_organization_external_id as district_agency_code

    from district_prd_pst.roster.organization

    where
        organization.organization_type = 'DISTRICT'
        --and organization.district_geography_name_abbreviated = $state
        and organization.district_geography_name_abbreviated = '$STATE_ABR'

),

included_schools as (

    select
        included_districts.state as state,
        organization.organization_bid as school_bid,
        organization.custom_name as school_standard_name,
        included_districts.district_business_identifier as district_business_identifier,
        included_districts.district_standard_name as district_standard_name,
        included_districts.district_agency_code as district_agency_code,
        organization.partner_id as partner_id

    from district_prd_pst.roster.organization

    inner join included_districts
        on organization.partner_id = included_districts.partner_id

    where 
        organization.organization_type = 'SCHOOL'
    
),

included_terms as (

    select
        partner_id,
        term_bid,
        term_number,
        name as term_name,
        season_short_name as season_code,
        academic_year_name,
        cast(substr(academic_year_name, 1, 4) as integer) as academic_year_code

    from district_prd_pst.roster.term

    where
        term_number = $TERM_NUMBER

),

included_students as (
    select        
        included_schools.state as state,
        included_schools.district_business_identifier as district_business_identifier,
        included_schools.district_standard_name as district_standard_name,
        included_schools.district_agency_code as district_agency_code,
        included_schools.partner_id as partner_id,
        included_schools.school_bid as school_business_identifier,
        included_schools.school_standard_name as school_standard_name,
        included_terms.term_number as term_number,
        included_terms.term_bid as term_bid,
        
        CASE
            WHEN student_school_enrollment.grade_bid IN (13, 16, 17) THEN 0
            WHEN student_school_enrollment.grade_bid = 14 THEN -1
            WHEN student_school_enrollment.grade_bid IN (1,2,3,4,5,6,7,8,9,10,11,12)
                THEN student_school_enrollment.grade_bid
            ELSE NULL
        END AS grade_ordinal,

        student_school_enrollment.student_bid as student_business_identifier,
        eg.nwea_ethnic_group_name,
        case(eg.nwea_ethnic_group_name)
           when 'American Indian or Alaska Native' then 1
           when 'Asian' then 2
           when 'Black or African American' then 3
           when 'Hispanic or Latino' then 4
           when 'Multi-ethnic' then 5
           when 'Native Hawaiian or Other Pacific Islander' then 6
           when 'Not Specified or Other' then 7
           when 'White' then 8
        end as nwea_ethnic_group_code,
        student.gender as student_gender,
        upper(trim(student.name_first)) as student_first_name,
        upper(trim(student.name_last)) as student_last_name,
        nvl(try_to_number(student.state_student_external_id), NULL) as student_state_id,
        nvl(try_to_number(student.district_student_external_id), NULL) as student_id,
        student.date_of_birth as dob,
        to_varchar(student.student_dob_at_first_of_month, 'YYYYMM')::number as DOB_YYYY_MM
        
    from included_schools
    
    inner join district_prd_pst.roster.student_school_enrollment student_school_enrollment
        on included_schools.school_bid = student_school_enrollment.organization_bid
        and student_school_enrollment.primary_yn = true

    inner join included_terms
        on student_school_enrollment.partner_id = included_terms.partner_id
        and student_school_enrollment.term_bid = included_terms.term_bid        

    inner join district_prd_pst.roster.student student
        on student_school_enrollment.student_bid = student.student_bid

    left outer join district_PRD_pst.roster.ethnic_group eg
        on student_school_enrollment.ethnic_group_id = eg.ethnic_group_id
        
),

included_test_events as (

    select
        included_students.*,
        test_event.test_event_bid as test_event_business_identifier,
        test_event.score::int as irit,
        test_event.standard_error::DECIMAL(5,2) as sem,
        test.name as test_name,
        
        test.test_bid as test_key,
        
        CASE (course.measurement_scale_bid)
           WHEN 12 THEN 7 -- SNOWFLAKE RECORDS SPANISH-DELIVERED READING TEST (LANGUAGE ARTS?) ARE ODED 0 NOT 7 PER LINKING DOCS SPECS.
           ELSE course.measurement_scale_bid
        END AS measurement_scale_bid,
        course.measurement_scale_bid as measurement_scale_bid_snowflake,
        course.subject as subject,
        cs_tests.test_grade_low as test_grade_low,
        cs_tests.test_grade_high as test_grade_high,
        test_event.event_end_datetime as testdate,
        cs_tests.language_id as language_id,
        row_number() over (
            PARTITION BY  included_students.student_business_identifier,  included_students.TERM_NUMBER,  course.MEASUREMENT_SCALE_BID
            ORDER BY test_event.score DESC
        ) as score_rank,
        course.reportable_yn,
        test_event.valid_event_yn,
        test_event.growth_event_yn,
        test_event.grd_valid_test_event_yn,
        test_event.GRD_MPG_RESCORED_RIT

    from district_prd_pst.map_growth.test_event test_event

    inner join included_students
        on test_event.student_bid = included_students.student_business_identifier
        and test_event.partner_id = included_students.partner_id
        and test_event.term_bid = included_students.term_bid

    inner join district_prd_pst.content.course course
        on test_event.course_id = course.course_id

    inner join district_prd_pst.content.test test
        on test_event.test_id = test.test_id

    left outer join research_prd_grd_db.grd.content_supply_tests cs_tests
        on cast(split_part(test.test_bid, '-', 2) as number) = cs_tests.test_key

    where
        test_event.valid_event_yn = true
        and test_event.growth_event_yn = true
        and test_event.score is not null
        --AND test.name IN (SELECT TRIM(VALUE) FROM TABLE(SPLIT_TO_TABLE($testnames, '|')))
        and TEST_NAME in ($TESTNAMES)
       
)

select
    test_event_business_identifier,
    state,
    district_business_identifier,
    district_standard_name,
    district_agency_code,
    school_business_identifier,
    school_standard_name,
    grade_ordinal,
    student_business_identifier,
    nwea_ethnic_group_name,
    nwea_ethnic_group_code,
    irit,
    sem,
    test_name,
    test_key,
    student_gender,
    student_first_name,
    student_last_name,
    student_state_id,
    student_id,
    measurement_scale_bid,
    measurement_scale_bid_snowflake,
    subject,
    term_number,
    test_grade_low,
    test_grade_high,
    testdate,
    language_id,
    dob,
    dob_yyyy_mm,
    score_rank,
    growth_event_yn

from included_test_events
;
