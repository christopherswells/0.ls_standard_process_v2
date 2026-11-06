-- ============================================================================
-- merge_linking_study_to_studysample_qa_v2.sql
--
-- Creates the study-sample QA table by matching partner data to MAP Growth
-- records through seven ordered match phases.
--
-- Required template variables supplied by the Python runner:
--   $MERGED_TABLE_NAME
--   $PARTNER_TABLE_NAME
--   $SETTINGS_TABLE_NAME
--   $MAP_GROWTH_TABLE_NAME
-- ============================================================================

CREATE OR REPLACE TABLE IDENTIFIER('$MERGED_TABLE_NAME') AS

WITH partner_keyed AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                D.D_AGENCYCODE_CLEAN,
                D.D_STATE_STID,
                D.D_LOCAL_STID,
                D.D_LNAME,
                D.D_FNAME
        ) AS DUMMY_ID,
        D.*,
        S.SETTINGS_D_MAPGROWTH_TEST_NAME,
        S.SETTINGS_STUDY_TYPE,
        S.SETTINGS_GRADE_LIST,
        S.SETTINGS_TERM,
        S.SETTINGS_CUTS_SUBJECT,

        -- Normalized keys computed once and reused in every phase.
        TRIM(UPPER(S.SETTINGS_D_MAPGROWTH_TEST_NAME))       AS K_TEST,
        TRIM(UPPER(D.D_AGENCYCODE))                         AS K_AGENCY,
        TRY_CAST(TRIM(D.D_STATE_STID) AS NUMBER)            AS K_STATE_ID,
        TRY_CAST(TRIM(D.D_LOCAL_STID) AS NUMBER)            AS K_LOCAL_ID,
        UPPER(REGEXP_REPLACE(D.D_FNAME, '[^A-Za-z]', ''))   AS K_FN,
        UPPER(REGEXP_REPLACE(D.D_LNAME, '[^A-Za-z]', ''))   AS K_LN,
        TRY_TO_DATE(D.D_DOB_CLEAN)                          AS K_DOB,
        TRY_CAST(D.D_GRADE_CLEAN AS NUMBER)                 AS K_GRADE

    FROM IDENTIFIER('$PARTNER_TABLE_NAME') D

    LEFT JOIN IDENTIFIER('$SETTINGS_TABLE_NAME') S
        ON UPPER(TRIM(D.D_SUBJECT)) = UPPER(TRIM(S.SETTINGS_D_SUBJECT))

    -- Exclude partner rows outside the configured linking-study grades before
    -- executing the match phases.
    WHERE ARRAY_CONTAINS(
        TRY_CAST(D.D_GRADE_CLEAN AS NUMBER)::VARIANT,
        PARSE_JSON(S.SETTINGS_GRADE_LIST)
    )
),

map_keyed AS (
    SELECT
        M.STUDENT_BUSINESS_IDENTIFIER,
        M.TEST_EVENT_BUSINESS_IDENTIFIER,
        M.DOB,
        M.GRADE_ORDINAL,
        TRIM(UPPER(M.TEST_NAME))                                      AS K_TEST,
        TRIM(UPPER(M.DISTRICT_AGENCY_CODE))                           AS K_AGENCY,
        TRY_CAST(TRIM(M.STUDENT_STATE_ID) AS NUMBER)                  AS K_STATE_ID,
        TRY_CAST(TRIM(M.STUDENT_ID) AS NUMBER)                        AS K_ID,
        UPPER(REGEXP_REPLACE(M.STUDENT_FIRST_NAME, '[^A-Za-z]', ''))  AS K_FN,
        UPPER(REGEXP_REPLACE(M.STUDENT_LAST_NAME, '[^A-Za-z]', ''))   AS K_LN

    FROM IDENTIFIER('$MAP_GROWTH_TABLE_NAME') M

    WHERE TRIM(UPPER(M.TEST_NAME)) IN (
        SELECT DISTINCT K_TEST
        FROM partner_keyed
        WHERE K_TEST IS NOT NULL
    )
),

-- Phase 1: exact test, district, name, and DOB, with an exact state or local ID.
phase1 AS (
    SELECT
        D.DUMMY_ID,
        M.STUDENT_BUSINESS_IDENTIFIER,
        M.TEST_EVENT_BUSINESS_IDENTIFIER,
        'PHASE_1' AS MATCH_TYPE,
        'EXACT_ID_EXACT_NAME_DISTRICT_DOB' AS MATCH_DESCRIPTION

    FROM partner_keyed D

    JOIN map_keyed M
        ON D.K_TEST = M.K_TEST
       AND D.K_AGENCY = M.K_AGENCY
       AND D.K_FN = M.K_FN
       AND D.K_LN = M.K_LN
       AND D.K_DOB = M.DOB

    WHERE M.K_STATE_ID = D.K_STATE_ID
       OR M.K_ID = D.K_LOCAL_ID
),

-- Phase 2: exact test, district, and DOB; IDs and names may be cross-matched.
phase2 AS (
    SELECT
        D.DUMMY_ID,
        M.STUDENT_BUSINESS_IDENTIFIER,
        M.TEST_EVENT_BUSINESS_IDENTIFIER,
        'PHASE_2' AS MATCH_TYPE,
        'MIXED_ID_MIXED_NAME_district_DOB' AS MATCH_DESCRIPTION

    FROM partner_keyed D

    JOIN map_keyed M
        ON D.K_TEST = M.K_TEST
       AND D.K_AGENCY = M.K_AGENCY
       AND D.K_DOB = M.DOB

    WHERE (
              M.K_STATE_ID IN (D.K_STATE_ID, D.K_LOCAL_ID)
           OR M.K_ID IN (D.K_STATE_ID, D.K_LOCAL_ID)
          )
      AND (
              (D.K_FN = M.K_FN AND D.K_LN = M.K_LN)
           OR (D.K_FN = M.K_LN AND D.K_LN = M.K_FN)
          )
      AND NOT EXISTS (
          SELECT 1
          FROM phase1 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
),

-- Phase 3: same as phase 2, but grade replaces DOB.
phase3 AS (
    SELECT
        D.DUMMY_ID,
        M.STUDENT_BUSINESS_IDENTIFIER,
        M.TEST_EVENT_BUSINESS_IDENTIFIER,
        'PHASE_3' AS MATCH_TYPE,
        'MIXED_ID_MIXED_NAME_district_grade(notDOB)' AS MATCH_DESCRIPTION

    FROM partner_keyed D

    JOIN map_keyed M
        ON D.K_TEST = M.K_TEST
       AND D.K_AGENCY = M.K_AGENCY
       AND D.K_GRADE = M.GRADE_ORDINAL

    WHERE (
              M.K_STATE_ID IN (D.K_STATE_ID, D.K_LOCAL_ID)
           OR M.K_ID IN (D.K_STATE_ID, D.K_LOCAL_ID)
          )
      AND (
              (D.K_FN = M.K_FN AND D.K_LN = M.K_LN)
           OR (D.K_FN = M.K_LN AND D.K_LN = M.K_FN)
          )
      AND NOT EXISTS (
          SELECT 1
          FROM phase1 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase2 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
),

-- Phase 4: no ID equality required; exact names, DOB, district, and grade.
-- The phase is allowed only when no partner/MAP ID pair has equal length.
phase4 AS (
    SELECT
        D.DUMMY_ID,
        M.STUDENT_BUSINESS_IDENTIFIER,
        M.TEST_EVENT_BUSINESS_IDENTIFIER,
        'PHASE_4' AS MATCH_TYPE,
        'noIDmatch_EXACT_NAMES_DOB_DISTRICT_IDS_DIFFERENT_LENGTHS' AS MATCH_DESCRIPTION

    FROM partner_keyed D

    JOIN map_keyed M
        ON D.K_TEST = M.K_TEST
       AND D.K_AGENCY = M.K_AGENCY
       AND D.K_FN = M.K_FN
       AND D.K_LN = M.K_LN
       AND D.K_DOB = M.DOB
       AND D.K_GRADE = M.GRADE_ORDINAL

    WHERE NULLIF(TRIM(D.K_FN), '') IS NOT NULL
      AND NULLIF(TRIM(D.K_LN), '') IS NOT NULL
      AND NOT (
              (
                  D.K_STATE_ID IS NOT NULL
                  AND M.K_STATE_ID IS NOT NULL
                  AND LENGTH(TO_VARCHAR(D.K_STATE_ID)) = LENGTH(TO_VARCHAR(M.K_STATE_ID))
              )
           OR (
                  D.K_STATE_ID IS NOT NULL
                  AND M.K_ID IS NOT NULL
                  AND LENGTH(TO_VARCHAR(D.K_STATE_ID)) = LENGTH(TO_VARCHAR(M.K_ID))
              )
           OR (
                  D.K_LOCAL_ID IS NOT NULL
                  AND M.K_STATE_ID IS NOT NULL
                  AND LENGTH(TO_VARCHAR(D.K_LOCAL_ID)) = LENGTH(TO_VARCHAR(M.K_STATE_ID))
              )
           OR (
                  D.K_LOCAL_ID IS NOT NULL
                  AND M.K_ID IS NOT NULL
                  AND LENGTH(TO_VARCHAR(D.K_LOCAL_ID)) = LENGTH(TO_VARCHAR(M.K_ID))
              )
          )
      AND NOT EXISTS (
          SELECT 1
          FROM phase1 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase2 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase3 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
),

-- Phase 5: no ID equality required; fuzzy names plus DOB, grade, and district.
-- The phase is allowed only when no partner/MAP ID pair has equal length.
phase5 AS (
    SELECT
        D.DUMMY_ID,
        M.STUDENT_BUSINESS_IDENTIFIER,
        M.TEST_EVENT_BUSINESS_IDENTIFIER,
        'PHASE_5' AS MATCH_TYPE,
        'fuzzy_noIDmatch__NAME_jw85_DOB_GRADE_DISTRICT_IDS_DIFFERENT_LENGTHS' AS MATCH_DESCRIPTION

    FROM partner_keyed D

    JOIN map_keyed M
        ON D.K_TEST = M.K_TEST
       AND D.K_AGENCY = M.K_AGENCY
       AND D.K_DOB = M.DOB
       AND D.K_GRADE = M.GRADE_ORDINAL

    WHERE NULLIF(TRIM(D.K_FN), '') IS NOT NULL
      AND NULLIF(TRIM(D.K_LN), '') IS NOT NULL
      AND (
              (
                  JAROWINKLER_SIMILARITY(D.K_FN, M.K_FN) >= 85
                  AND JAROWINKLER_SIMILARITY(D.K_LN, M.K_LN) >= 85
              )
           OR (
                  JAROWINKLER_SIMILARITY(D.K_FN, M.K_LN) >= 85
                  AND JAROWINKLER_SIMILARITY(D.K_LN, M.K_FN) >= 85
              )
          )
      AND NOT (
              (
                  D.K_STATE_ID IS NOT NULL
                  AND M.K_STATE_ID IS NOT NULL
                  AND LENGTH(TO_VARCHAR(D.K_STATE_ID)) = LENGTH(TO_VARCHAR(M.K_STATE_ID))
              )
           OR (
                  D.K_STATE_ID IS NOT NULL
                  AND M.K_ID IS NOT NULL
                  AND LENGTH(TO_VARCHAR(D.K_STATE_ID)) = LENGTH(TO_VARCHAR(M.K_ID))
              )
           OR (
                  D.K_LOCAL_ID IS NOT NULL
                  AND M.K_STATE_ID IS NOT NULL
                  AND LENGTH(TO_VARCHAR(D.K_LOCAL_ID)) = LENGTH(TO_VARCHAR(M.K_STATE_ID))
              )
           OR (
                  D.K_LOCAL_ID IS NOT NULL
                  AND M.K_ID IS NOT NULL
                  AND LENGTH(TO_VARCHAR(D.K_LOCAL_ID)) = LENGTH(TO_VARCHAR(M.K_ID))
              )
          )
      AND NOT EXISTS (
          SELECT 1
          FROM phase1 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase2 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase3 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase4 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
),

-- Phase 6: PII absent; match on test, district, grade, and an ID combination.
phase6 AS (
    SELECT
        D.DUMMY_ID,
        M.STUDENT_BUSINESS_IDENTIFIER,
        M.TEST_EVENT_BUSINESS_IDENTIFIER,
        'PHASE_6' AS MATCH_TYPE,
        'id_district_and_grade_only_PII_NOT_PROVIDED' AS MATCH_DESCRIPTION

    FROM partner_keyed D

    JOIN map_keyed M
        ON D.K_TEST = M.K_TEST
       AND D.K_AGENCY = M.K_AGENCY
       AND D.K_GRADE = M.GRADE_ORDINAL

    WHERE NULLIF(TRIM(D.K_FN), '') IS NULL
      AND NULLIF(TRIM(D.K_LN), '') IS NULL
      AND D.K_DOB IS NULL
      AND (
              M.K_STATE_ID IN (D.K_STATE_ID, D.K_LOCAL_ID)
           OR M.K_ID IN (D.K_STATE_ID, D.K_LOCAL_ID)
          )
      AND NOT EXISTS (
          SELECT 1
          FROM phase1 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase2 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase3 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase4 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase5 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
),

-- Phase 7: district may differ; require ID, exact PII, grade, and test.
phase7 AS (
    SELECT
        D.DUMMY_ID,
        M.STUDENT_BUSINESS_IDENTIFIER,
        M.TEST_EVENT_BUSINESS_IDENTIFIER,
        'PHASE_7' AS MATCH_TYPE,
        'charter_schools_district_not_matching__id_AND_EXACT_PII' AS MATCH_DESCRIPTION

    FROM partner_keyed D

    JOIN map_keyed M
        ON D.K_TEST = M.K_TEST
       AND D.K_GRADE = M.GRADE_ORDINAL
       AND D.K_FN = M.K_FN
       AND D.K_LN = M.K_LN
       AND D.K_DOB = M.DOB

    WHERE (
              M.K_STATE_ID IN (D.K_STATE_ID, D.K_LOCAL_ID)
           OR M.K_ID IN (D.K_STATE_ID, D.K_LOCAL_ID)
          )
      AND NOT EXISTS (
          SELECT 1
          FROM phase1 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase2 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase3 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase4 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase5 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
      AND NOT EXISTS (
          SELECT 1
          FROM phase6 P
          WHERE P.DUMMY_ID = D.DUMMY_ID
      )
),

all_matches AS (
    SELECT * FROM phase1
    UNION ALL
    SELECT * FROM phase2
    UNION ALL
    SELECT * FROM phase3
    UNION ALL
    SELECT * FROM phase4
    UNION ALL
    SELECT * FROM phase5
    UNION ALL
    SELECT * FROM phase6
    UNION ALL
    SELECT * FROM phase7
)

SELECT
    COALESCE(AM.MATCH_TYPE, 'UNMATCHED') AS MATCH_TYPE,
    COALESCE(AM.MATCH_DESCRIPTION, 'UNMATCHED') AS MATCH_DESCRIPTION,
    D.FLAG_REASON,

    AM.STUDENT_BUSINESS_IDENTIFIER AS M_STUDENT_BUSINESS_IDENTIFIER,
    M.TEST_EVENT_BUSINESS_IDENTIFIER AS M_TEST_EVENT_BUSINESS_IDENTIFIER,

    M.STUDENT_STATE_ID AS M_STUDENT_STATE_ID,
    D.D_STATE_STID_CLEAN AS D_STATE_STID,
    M.STUDENT_ID AS M_STUDENT_ID,
    D.D_LOCAL_STID_CLEAN AS D_LOCAL_STID,

    M.STUDENT_FIRST_NAME AS M_STUDENT_FIRST_NAME,
    D.D_FNAME,
    M.STUDENT_LAST_NAME AS M_STUDENT_LAST_NAME,
    D.D_LNAME,
    D.D_MNAME,

    M.DOB AS M_DOB,
    D.D_DOB,
    D.D_DOB_CLEAN,

    M.STUDENT_GENDER AS M_STUDENT_GENDER,
    D.D_SEX,
    M.NWEA_ETHNIC_GROUP_NAME AS M_NWEA_ETHNIC_GROUP_NAME,
    D.D_ETHNICITY,
    D.D_RACE,

    M.GRADE_ORDINAL AS M_GRADE_ORDINAL,
    D.D_GRADE,
    D.D_GRADE_CLEAN,

    M.DISTRICT_AGENCY_CODE AS M_DISTRICT_AGENCY_CODE,
    D.D_AGENCYCODE,
    D.D_DISTRICTNAME,
    M.DISTRICT_BUSINESS_IDENTIFIER AS M_DISTRICT_BUSINESS_IDENTIFIER,
    M.DISTRICT_STANDARD_NAME AS M_DISTRICT_STANDARD_NAME,
    M.STATE AS M_STATE,
    M.SCHOOL_BUSINESS_IDENTIFIER AS M_SCHOOL_BUSINESS_IDENTIFIER,
    M.SCHOOL_STANDARD_NAME AS M_SCHOOL_STANDARD_NAME,
    D.D_SCHOOLNAME,

    M.SUBJECT AS M_SUBJECT,
    D.D_SUBJECT,
    M.TEST_NAME AS M_TEST_NAME,
    D.D_TESTNAME,
    M.MEASUREMENT_SCALE_BID AS M_MEASUREMENT_SCALE_BID,
    M.MEASUREMENT_SCALE_BID_SNOWFLAKE AS M_MEASUREMENT_SCALE_BID_SNOWFLAKE,

    COALESCE(
        TRY_TO_NUMBER(
            REGEXP_SUBSTR(
                UPPER(D.D_TESTNAME),
                'GRADE\\s*0?([0-9]{1,2})',
                1,
                1,
                'e',
                1
            )
        ),
        CASE
            WHEN REGEXP_LIKE(UPPER(D.D_TESTNAME), 'THIRD\\s*GRADE') THEN 3
            WHEN REGEXP_LIKE(UPPER(D.D_TESTNAME), 'FOURTH\\s*GRADE') THEN 4
            WHEN REGEXP_LIKE(UPPER(D.D_TESTNAME), 'FIFTH\\s*GRADE') THEN 5
            WHEN REGEXP_LIKE(UPPER(D.D_TESTNAME), 'SIXTH\\s*GRADE') THEN 6
            WHEN REGEXP_LIKE(UPPER(D.D_TESTNAME), 'SEVENTH\\s*GRADE') THEN 7
            WHEN REGEXP_LIKE(UPPER(D.D_TESTNAME), 'EIGHTH\\s*GRADE') THEN 8
        END
    ) AS D_GRADE_OF_PARTNER_TEST,

    M.IRIT AS M_IRIT,
    M.SEM AS M_SEM,
    D.D_SS_CLEAN AS D_SS,
    D.D_PLCODE,
    D.D_PLDESC,
    D.D_RETEST,

    M.TESTDATE AS M_TESTDATE,
    TO_CHAR(M.TESTDATE, 'MM/DD/YYYY') AS M_FORMATTED_TESTDATE,
    D.D_TESTDATE,
    D.D_TESTDATE_CLEAN,
    M.TERM_NUMBER AS M_TERM_NUMBER,
    D.D_TERM,

    M.TEST_GRADE_LOW AS M_TEST_GRADE_LOW,
    M.TEST_GRADE_HIGH AS M_TEST_GRADE_HIGH,
    M.LANGUAGE_ID AS M_LANGUAGE_ID,

    D.D_SPED,
    D.D_SEC504,
    D.D_IEP,
    D.D_ELL,
    D.D_FRL,

    D.SETTINGS_CUTS_SUBJECT,
    D.SETTINGS_STUDY_TYPE,
    D.SETTINGS_D_MAPGROWTH_TEST_NAME,
    D.SETTINGS_GRADE_LIST,
    D.SETTINGS_TERM,

    CASE
        WHEN ARRAY_CONTAINS(
            TRY_CAST(D.D_GRADE_CLEAN AS NUMBER)::VARIANT,
            PARSE_JSON(D.SETTINGS_GRADE_LIST)
        ) THEN 1
        ELSE 0
    END AS D_GRADE_CLEAN_IN_SETTINGS_GRADE_LIST,

    CASE
        WHEN ARRAY_CONTAINS(
            M.GRADE_ORDINAL::VARIANT,
            PARSE_JSON(D.SETTINGS_GRADE_LIST)
        ) THEN 1
        ELSE 0
    END AS M_GRADE_ORDINAL_IN_SETTINGS_GRADE_LIST,

    D.D_FILENAMEFROMDISTRICT

FROM partner_keyed D

LEFT JOIN all_matches AM
    ON AM.DUMMY_ID = D.DUMMY_ID

LEFT JOIN IDENTIFIER('$MAP_GROWTH_TABLE_NAME') M
    ON M.STUDENT_BUSINESS_IDENTIFIER = AM.STUDENT_BUSINESS_IDENTIFIER
   AND M.TEST_EVENT_BUSINESS_IDENTIFIER = AM.TEST_EVENT_BUSINESS_IDENTIFIER

ORDER BY
    AM.MATCH_TYPE,
    D.D_STATE_STID,
    D.D_LOCAL_STID,
    D.D_LNAME,
    D.D_FNAME
;
