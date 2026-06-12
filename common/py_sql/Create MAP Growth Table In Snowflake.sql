/*
    Create  MAP DATA TABLE
    
    USE ROLE RESEARCH_PRD_MAPGROWTH_PSYCHOMETRIC_SOLUTIONS_FR;
    USE WAREHOUSE RESEARCH_PRD_MAPGROWTH_PSYCHOMETRIC_SOLUTIONS_WH;
    USE DATABASE RESEARCH_PRD_GRD_DB;


    SET TERM_NUMBER = 202402;  --varchar in MAP.  see linking study planning form for MAP term to use.
    SET STATE_CODE = 'MD';    --code to be used in output
    SET STATE_NAME = 'MARYLAND'; --state name as exists in MAP testevent view



 */
/*
 cleaning done prior for join fields.  need to document.
 eg. fname is uppder and trimmed.  state id numerical with
 nulls converted to -1 in map -99 in district so they wont merge.

*/

CREATE TABLE $STATE_ABR$DATA_YEAR_STUDYSAMPLE_QA AS

SELECT
    /* ======================
       Match classification
       ====================== */
    CASE
        /* Phase 1: all IDs + names + DOB */
        WHEN
            /* state OR local ID */
            (
                NULLIF(TRIM(M.STUDENT_STATE_ID), '') IS NOT NULL
                AND NULLIF(TRIM(D_STATE_STID), '') IS NOT NULL
                AND NULLIF(TRIM(M.STUDENT_STATE_ID), '') = NULLIF(TRIM(D_STATE_STID), '')
            OR
                NULLIF(TRIM(M.STUDENT_ID), '') IS NOT NULL
                AND NULLIF(TRIM(D_LOCAL_STID), '') IS NOT NULL
                AND NULLIF(TRIM(M.STUDENT_ID), '') = NULLIF(TRIM(D_LOCAL_STID), '')
            )
            /* name */
        AND UPPER(REGEXP_REPLACE(D_FNAME, '[^A-Z]', ''))
            = UPPER(REGEXP_REPLACE(M.STUDENT_FIRST_NAME, '[^A-Z]', ''))
        AND UPPER(REGEXP_REPLACE(D_LNAME, '[^A-Z]', ''))
            = UPPER(REGEXP_REPLACE(M.STUDENT_LAST_NAME, '[^A-Z]', ''))
            /* DOB */
        AND D_DOB_ASDATE = M.R_DOB
        THEN 'PHASE_1_FULL_ID_NAME_DOB'

        /* Phase 2: ID + name + DOB */
        WHEN
            (
                NULLIF(TRIM(M.STUDENT_STATE_ID), '') = NULLIF(TRIM(D_STATE_STID), '')
            OR  NULLIF(TRIM(M.STUDENT_ID), '')       = NULLIF(TRIM(D_LOCAL_STID), '')
            )
        AND UPPER(REGEXP_REPLACE(D_FNAME, '[^A-Z]', ''))
            = UPPER(REGEXP_REPLACE(M.STUDENT_FIRST_NAME, '[^A-Z]', ''))
        AND UPPER(REGEXP_REPLACE(D_LNAME, '[^A-Z]', ''))
            = UPPER(REGEXP_REPLACE(M.STUDENT_LAST_NAME, '[^A-Z]', ''))
        AND D_DOB_ASDATE = M.R_DOB
        THEN 'PHASE_2_ID_NAME_DOB'

        /* Phase 3: ID + DOB (no name) */
        WHEN
            (
                NULLIF(TRIM(M.STUDENT_STATE_ID), '') = NULLIF(TRIM(D_STATE_STID), '')
            OR  NULLIF(TRIM(M.STUDENT_ID), '')       = NULLIF(TRIM(D_LOCAL_STID), '')
            )
        AND D_DOB_ASDATE = M.R_DOB
        THEN 'PHASE_3_ID_DOB'

        ELSE 'UNMATCHED'
    END AS MATCH_TYPE,

    /* ======================
       Your existing columns
       ====================== */
    M.STUDENT_BUSINESS_IDENTIFIER,
    D_GRADE,
    M.GRADE_ORDINAL AS M_GRADE,

    CASE WHEN M.STUDENT_STATE_ID = -1 THEN NULL ELSE M.STUDENT_STATE_ID END AS M_STATE_STID,
    CASE WHEN D_STATE_STID     = -99 THEN NULL ELSE D_STATE_STID     END AS D_STATE_STID,

    CASE WHEN M.STUDENT_ID = -1 THEN NULL ELSE M.STUDENT_ID END AS M_LOCAL_STID,
    CASE WHEN D_LOCAL_STID = -99 THEN NULL ELSE D_LOCAL_STID END AS D_LOCAL_STID,

    D_SUBJECT,
    D_SUBJECT_CODE,
    M.SUBJECT AS M_SUBJECT,
    M.MEASUREMENT_SCALE_BID,
    M.TEST_NAME,
    M.TEST_KEY,
    M.TESTDATE AS M_TESTDATE,
    D_MAPGROWTH_TEST_NAME,

    M.STUDENT_LAST_NAME,
    D_LNAME,
    M.STUDENT_FIRST_NAME,
    D_FNAME,

    M.R_DOB,
    D_DOB,

    D_DISTRICTNAME,
    M.DISTRICT_STANDARD_NAME,
    D_FILENAMEFROMDISTRICT,
    D_AGENCYCODE,
    M.DISTRICT_AGENCY_CODE AS M_AGENCYCODE,

    M.DISTRICT_BUSINESS_IDENTIFIER,
    M.DISTRICT_STANDARD_NAME AS M_DISTRICTNAME,
    '$STATE_ABR' AS STATE,

    D_TERM,
    M.SCHOOL_BUSINESS_IDENTIFIER,
    M.SCHOOL_STANDARD_NAME AS SCHOOLNAME,
    D.D_SCHOOLNAME,

    M.STUDENT_GENDER AS M_SEX,
    D_SEX,

    COALESCE(
        CASE WHEN UPPER(D_SEX) IN ('M','MALE','1') THEN 1
             WHEN UPPER(D_SEX) IN ('F','FEMALE','0') THEN 0 END,
        CASE WHEN UPPER(M.STUDENT_GENDER) IN ('M','MALE','1') THEN 1
             WHEN UPPER(M.STUDENT_GENDER) IN ('F','FEMALE','0') THEN 0 END
    ) AS SEX,

    D_ETHNICITY,
    D_RACE,
    M.NWEA_ETHNIC_GROUP_NAME,
    M.IRIT,
    M.SEM,
    D_SS,
    '' AS SS_ADJ,

    D_PLCODE,
    D_PLDESC,

    '' AS D_DUMMYID,
    D.D_TESTDATE,
    D.D_SPED,
    D.D_ELL,
    D.D_IEP,
    D.D_SEC504,
    D.D_FRL,
    D.D_RETEST,
    TEST_GRADE_LOW,
    TEST_GRADE_HIGH

FROM LINKING_STUDIES.$STATE_ABR$DATA_YEAR_LINKINGSTUDY_PARTNERDATA D
JOIN LINKING_STUDIES.$STATE_ABR$DATA_YEAR_MAPDATA M
  ON M.TEST_NAME = D_MAPGROWTH_TEST_NAME
 AND (
        NULLIF(TRIM(M.STUDENT_STATE_ID), '') = NULLIF(TRIM(D_STATE_STID), '')
     OR NULLIF(TRIM(M.STUDENT_ID), '')       = NULLIF(TRIM(D_LOCAL_STID), '')
     OR D_DOB_ASDATE = M.R_DOB
    )

QUALIFY ROW_NUMBER() OVER (
    PARTITION BY
        M.STUDENT_BUSINESS_IDENTIFIER,
        M.TEST_KEY
    ORDER BY
        CASE
            WHEN MATCH_TYPE = 'PHASE_1_FULL_ID_NAME_DOB' THEN 1
            WHEN MATCH_TYPE = 'PHASE_2_ID_NAME_DOB'      THEN 2
            WHEN MATCH_TYPE = 'PHASE_3_ID_DOB'           THEN 3
            ELSE 4
        END
) = 1

ORDER BY M.STUDENT_BUSINESS_IDENTIFIER;
