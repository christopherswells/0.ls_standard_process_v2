# -*- coding: utf-8 -*-
"""
Consolidated wide-to-long pivot for linking-study partner data.

Business rules implemented in this version
------------------------------------------
1. Do not merge df_long to settings_xl.
2. Do not create or retain settings-derived fields.
3. Remove exact duplicates, retaining the first wide-file occurrence.
4. Exclude long rows when no valid score-bearing field exists among
   SS, PLCODE, PLDESC, and PL when present.
5. Do not save all-invalid-score rows in removed_records.parquet.
6. Save exact duplicate long rows in removed_records.parquet, unless
   they also have no valid score-bearing field.
7. Keep FLAG_REASON in df_long.
8. Preserve upstream missing_grade, incorrect_term, and
   test_date_out_of_range flags when supplied in FLAG_REASON or
   FLAGGED_REASON.
9. Remove any upstream non-numeric_ss flag and recalculate it only on
   records retained in df_long after D_SS_CLEAN has been created.
10. Flag invalid_score when exactly one available score-bearing field
    is valid.
11. Defensively remove AGENCYCODE.1 and D_AGENCYCODE.1.
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------
# Spyder sometimes gets screwy with the working directory
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pycode.settings import *


# =========================================================
# CONSTANTS
# =========================================================

UPSTREAM_FLAGS_TO_RETAIN = {
    "missing_grade",
    "incorrect_term",
    "test_date_out_of_range",
}

INVALID_SCORE_TEXT_VALUES = {
    "",
    "-",
    "--",
    "---",
    ".",
    "..",
    "...",
    "NA",
    "N/A",
    "N\\A",
    "N.A.",
    "NAN",
    "NULL",
    "NONE",
    "MISSING",
    "NOT AVAILABLE",
    "NOT APPLICABLE",
    "#N/A",
    "#NA",
}

LEGACY_AND_UNWANTED_COLUMNS = [
    "SETTINGS_STATE",
    "SETTINGS_TERM",
    "SETTINGS_STUDY_TYPE",
    "SETTINGS_D_SUBJECT",
    "SETTINGS_D_SUBJECT_CODE",
    "SETTINGS_CUTS_SUBJECT",
    "SETTINGS_D_MAPGROWTH_TEST_NAME",
    "SETTINGS_STUDY_GRADES",
    "SETTINGS_GRADE_LIST",
    "original_file_path",
    "ORIGINAL_FILE_PATH",
    "D_ORIGINAL_FILE_PATH",
    "AGENCYCODE.1",
    "D_AGENCYCODE.1",
]


# =========================================================
# GENERAL HELPERS
# =========================================================

def _normalize_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize missing values and uppercase column headers."""
    df = df.copy()
    df = df.where(pd.notna(df), pd.NA)
    df = df.replace(r"^\s*$", pd.NA, regex=True)
    df = df.astype("string")
    df.columns = [str(column).strip().upper() for column in df.columns]
    return df


def rename_columns_upper_with_prefix(
    df: pd.DataFrame,
    prefix: str = "D_",
) -> pd.DataFrame:
    """Uppercase all column names and prepend prefix."""
    df = df.copy()
    df.columns = [
        f"{prefix}{str(column).strip().upper()}"
        for column in df.columns
    ]
    return df


def append_removal_reason(
    df: pd.DataFrame,
    mask,
    reason: str,
) -> pd.DataFrame:
    """Append a reason to REMOVAL_REASON and mark rows for removal."""
    df = df.copy()
    mask = pd.Series(mask, index=df.index).fillna(False).astype(bool)
    current_reason = df.loc[mask, "REMOVAL_REASON"]

    df.loc[mask, "REMOVAL_REASON"] = np.where(
        current_reason.isna(),
        reason,
        current_reason.astype(str) + "|" + reason,
    )
    df.loc[mask, "REMOVE_RECORD"] = True
    return df


def append_flag_reason(
    df: pd.DataFrame,
    mask,
    reason: str,
) -> pd.DataFrame:
    """Append a non-removal QA reason to FLAG_REASON."""
    df = df.copy()
    mask = pd.Series(mask, index=df.index).fillna(False).astype(bool)
    current_reason = df.loc[mask, "FLAG_REASON"]

    df.loc[mask, "FLAG_REASON"] = np.where(
        current_reason.isna(),
        reason,
        current_reason.astype(str) + "|" + reason,
    )
    return df


def merge_flag_reason_values(
    df: pd.DataFrame,
    source_column: str,
    target_column: str = "FLAG_REASON",
) -> pd.DataFrame:
    """Append pipe-delimited flags from source_column to target_column."""
    df = df.copy()

    if source_column not in df.columns:
        return df

    if target_column not in df.columns:
        df[target_column] = pd.Series(pd.NA, index=df.index, dtype="string")

    source_values = (
        df[source_column]
        .astype("string")
        .replace(r"^\s*$", pd.NA, regex=True)
    )
    target_values = (
        df[target_column]
        .astype("string")
        .replace(r"^\s*$", pd.NA, regex=True)
    )
    source_present = source_values.notna()

    df.loc[source_present, target_column] = np.where(
        target_values.loc[source_present].isna(),
        source_values.loc[source_present],
        target_values.loc[source_present] + "|" + source_values.loc[source_present],
    )
    return df


def normalize_flag_token(value: str) -> str:
    """Normalize a flag token for comparison."""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def filter_flag_reasons(
    df: pd.DataFrame,
    allowed_reasons: set,
    flag_column: str = "FLAG_REASON",
) -> pd.DataFrame:
    """Keep only allowed pipe-delimited flags in flag_column."""
    df = df.copy()

    if flag_column not in df.columns:
        return df

    allowed_normalized = {
        normalize_flag_token(reason)
        for reason in allowed_reasons
    }

    def filter_value(value):
        if pd.isna(value):
            return pd.NA

        kept = []
        seen = set()

        for raw_reason in str(value).split("|"):
            normalized = normalize_flag_token(raw_reason)
            if normalized in allowed_normalized and normalized not in seen:
                kept.append(normalized)
                seen.add(normalized)

        return "|".join(kept) if kept else pd.NA

    df[flag_column] = df[flag_column].apply(filter_value).astype("string")
    return df


def sanitize_object_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convert object values to Parquet-safe values."""
    df = df.copy()

    def sanitize_value(value):
        if value is None:
            return None
        if isinstance(value, float) and pd.isna(value):
            return None
        if isinstance(value, (list, tuple, np.ndarray)):
            return str(list(value))
        return str(value).strip()

    for column in df.columns:
        if df[column].dtype == "object":
            df[column] = df[column].apply(sanitize_value)

    return df


def drop_unwanted_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Remove AGENCYCODE.1 aliases without affecting AGENCYCODE."""
    df = df.copy()
    unwanted_names = {"AGENCYCODE.1", "D_AGENCYCODE.1"}
    columns_found = [
        column
        for column in df.columns
        if str(column).strip().upper() in unwanted_names
    ]
    return df.drop(columns=columns_found, errors="ignore")


def drop_legacy_and_unwanted_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Drop legacy settings, source-path, and unwanted duplicate columns."""
    return df.drop(columns=LEGACY_AND_UNWANTED_COLUMNS, errors="ignore")


# =========================================================
# WIDE-TO-LONG PIVOT
# =========================================================

def pivot_scores_long_no_impute(
    combineddf: pd.DataFrame,
) -> pd.DataFrame:
    """Pivot subject score fields from wide to long without dropping rows."""
    df = combineddf.copy()

    suffix_pattern = re.compile(
        rf"^(?P<subject>.+)_(?P<suffix>{'|'.join(SUFFIXES)})$",
        re.IGNORECASE,
    )

    score_columns: List[str] = []
    subjects: List[str] = []
    column_to_subject_suffix = {}

    for column in df.columns:
        match = suffix_pattern.match(str(column))
        if match:
            subject = match.group("subject")
            suffix = match.group("suffix").upper()
            score_columns.append(column)
            subjects.append(subject)
            column_to_subject_suffix[column] = (subject, suffix)

    subjects = sorted(pd.unique(subjects))
    non_subject_fields = [
        column for column in df.columns if column not in score_columns
    ]
    long_parts = []

    for subject in subjects:
        subject_columns = [
            column
            for column in score_columns
            if column_to_subject_suffix[column][0] == subject
        ]

        temp = df[non_subject_fields + subject_columns].copy()
        temp["SUBJECT"] = subject
        temp = temp.rename(
            columns={
                column: column_to_subject_suffix[column][1]
                for column in subject_columns
            }
        )

        for suffix in SUFFIXES:
            if suffix not in temp.columns:
                temp[suffix] = pd.NA

        temp = temp[non_subject_fields + ["SUBJECT"] + SUFFIXES]
        long_parts.append(temp)

    if not long_parts:
        out = df[non_subject_fields].copy()
        out["SUBJECT"] = pd.NA
        for suffix in SUFFIXES:
            out[suffix] = pd.NA
        return out

    long_df = pd.concat(long_parts, ignore_index=True)
    existing_suffixes = [
        suffix for suffix in SUFFIXES if suffix in long_df.columns
    ]
    long_df[existing_suffixes] = long_df[existing_suffixes].replace(
        r"^\s*$",
        pd.NA,
        regex=True,
    )
    return long_df


# =========================================================
# EXACT DUPLICATES IN THE WIDE FILE
# =========================================================

def mark_exact_duplicates_in_combined_file(
    df: pd.DataFrame,
    ignored_columns: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, List[str]]:
    """Mark later copies of exact wide-file duplicates."""
    df = df.copy()

    default_ignored = {
        "FILENAMEFROMDISTRICT",
        "AGENCYCODE",
        "AGENCY_CODE",
        "FILENAME_FROM_DISTRICT",
        "SOURCE_FILENAME",
        "SOURCEFILE",
        "SOURCE_FILE",
        "INDEX",
        "LEVEL_0",
        "ROWNUM",
        "ROW_NUM",
        "ROWNUMBER",
        "ROW_NUMBER",
        "RECORDNUM",
        "RECORD_NUM",
        "RECORDNUMBER",
        "RECORD_NUMBER",
        "UNNAMED: 0",
    }

    if ignored_columns:
        default_ignored.update(
            str(column).strip().upper()
            for column in ignored_columns
        )

    def is_generated_or_ignored(column_name: str) -> bool:
        normalized = str(column_name).strip().upper()
        if normalized in default_ignored:
            return True

        generated_patterns = [
            r"^UNNAMED(?::|\s|_)*\d*$",
            r"^INDEX(?:_\d+)?$",
            r"^LEVEL_\d+$",
            r"^ROW_?NUM(?:BER)?$",
            r"^RECORD_?NUM(?:BER)?$",
            r"^SOURCE_?FILE(?:NAME)?$",
            r"^FILE_?NAME_?FROM_?DISTRICT$",
        ]
        return any(re.fullmatch(pattern, normalized) for pattern in generated_patterns)

    comparison_columns = [
        column
        for column in df.columns
        if not is_generated_or_ignored(column)
        and str(column).strip().upper() not in {
            "EXACT_DUPLICATE",
            "FLAG_REASON",
            "FLAGGED_REASON",
        }
    ]

    if not comparison_columns:
        raise ValueError("No columns remain for exact-duplicate comparison.")

    df["EXACT_DUPLICATE"] = df.duplicated(
        subset=comparison_columns,
        keep="first",
    )

    print(
        "Exact duplicate comparison used "
        f"{len(comparison_columns):,} columns."
    )
    print(
        "Exact duplicate wide-file rows marked: "
        f"{int(df['EXACT_DUPLICATE'].sum()):,}"
    )
    return df, comparison_columns


# =========================================================
# SCORE VALIDATION
# =========================================================

def is_invalid_score_value(value) -> bool:
    """Return True for missing/placeholder/zero score-field values."""
    if value is None or pd.isna(value):
        return True

    text = str(value).strip()
    if not text:
        return True

    normalized = re.sub(r"\s+", " ", text.upper()).strip()

    if normalized in INVALID_SCORE_TEXT_VALUES:
        return True
    if re.fullmatch(r"-+", normalized):
        return True
    if re.fullmatch(r"\.+", normalized):
        return True

    try:
        numeric_value = float(normalized.replace(",", ""))
        if np.isfinite(numeric_value) and numeric_value == 0:
            return True
    except (TypeError, ValueError):
        pass

    return False


def get_score_validation_masks(
    df: pd.DataFrame,
    score_columns: Optional[List[str]] = None,
) -> Tuple[pd.Series, pd.Series]:
    """
    Return masks for all-invalid scores and exactly-one-valid score.

    Zero valid fields: exclude from df_long and removed_records.
    Exactly one valid field: retain and flag invalid_score.
    Two or more valid fields: retain without invalid_score.
    """
    if score_columns is None:
        score_columns = ["D_SS", "D_PLCODE", "D_PLDESC", "D_PL"]

    available_score_columns = [
        column for column in score_columns if column in df.columns
    ]

    if not available_score_columns:
        raise ValueError(
            "None of the expected score columns were found. "
            f"Expected one or more of: {score_columns}"
        )

    invalid_score_matrix = pd.DataFrame(
        {
            column: df[column].apply(is_invalid_score_value)
            for column in available_score_columns
        },
        index=df.index,
    )

    valid_score_count = (~invalid_score_matrix).sum(axis=1)
    all_scores_invalid = valid_score_count.eq(0)
    retained_with_invalid_score = valid_score_count.eq(1)

    return (
        all_scores_invalid.astype(bool),
        retained_with_invalid_score.astype(bool),
    )


# =========================================================
# GRADE CLEANING
# =========================================================

grade_map = {
    1: ["1", "1ST", "ONE", "FIRST", "GRADE 1", "GRADE 01"],
    2: ["2", "2ND", "TWO", "SECOND", "GRADE 2", "GRADE 02"],
    3: ["3", "3RD", "THREE", "THIRD", "GRADE 3", "GRADE 03"],
    4: ["4", "4TH", "FOUR", "FOURTH", "GRADE 4", "GRADE 04"],
    5: ["5", "5TH", "FIVE", "FIFTH", "GRADE 5", "GRADE 05"],
    6: ["6", "6TH", "SIX", "SIXTH", "GRADE 6", "GRADE 06"],
    7: ["7", "7TH", "SEVEN", "SEVENTH", "GRADE 7", "GRADE 07"],
    8: ["8", "8TH", "EIGHT", "EIGHTH", "GRADE 8", "GRADE 08"],
    9: ["9", "9TH", "NINE", "NINTH", "GRADE 9", "GRADE 09"],
    10: ["10", "10TH", "TEN", "TENTH", "GRADE 10"],
    11: ["11", "11TH", "ELEVEN", "ELEVENTH", "GRADE 11"],
    12: ["12", "12TH", "TWELVE", "TWELFTH", "GRADE 12"],
    14: ["K", "KINDERGARTEN", "GRADE K"],
}


def normalize_grade_text(value) -> str:
    """Normalize grade text for lookup."""
    return re.sub(r"\s+", "", str(value).strip().upper())


reverse_grade_map = {
    normalize_grade_text(variant): grade_number
    for grade_number, variants in grade_map.items()
    for variant in variants
}


def add_clean_grade_column(
    df: pd.DataFrame,
    column: str,
) -> Tuple[pd.DataFrame, List]:
    """Create nullable Int64 grade-clean column."""
    df = df.copy()
    clean_column = f"{column}_CLEAN"

    def clean_grade(raw_value):
        if pd.isna(raw_value):
            return pd.NA

        raw_text = str(raw_value).strip()
        normalized_text = normalize_grade_text(raw_value)

        try:
            numeric_grade = float(raw_text)
            if numeric_grade.is_integer():
                numeric_grade = int(numeric_grade)
                if numeric_grade in grade_map:
                    return numeric_grade
        except (ValueError, TypeError):
            pass

        return reverse_grade_map.get(normalized_text, pd.NA)

    df[clean_column] = df[column].apply(clean_grade).astype("Int64")
    return df, df[clean_column].tolist()


# =========================================================
# INTEGER AND DATE CLEANING
# =========================================================

def add_clean_int_columns(
    df: pd.DataFrame,
    columns: List[str],
) -> pd.DataFrame:
    """Create nullable Int64 clean columns without dropping records."""
    df = df.copy()

    for column in columns:
        if column not in df.columns:
            print(f"Skipping missing integer column: {column}")
            continue

        clean_column = f"{column}_CLEAN"
        series = df[column].replace(r"^\s*$", pd.NA, regex=True)
        df[clean_column] = pd.to_numeric(
            series,
            errors="coerce",
        ).astype("Int64")

    return df


def _safe_parse_date(raw_value) -> Optional[datetime]:
    """Parse common district date formats."""
    if raw_value is None or pd.isna(raw_value):
        return None

    text = str(raw_value).strip()
    text = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?$", "", text)

    if re.fullmatch(r"\d+", text):
        digits = text

        if len(digits) == 8:
            candidates = [
                (int(digits[4:8]), int(digits[0:2]), int(digits[2:4])),
                (int(digits[0:4]), int(digits[4:6]), int(digits[6:8])),
            ]
            for year, month, day in candidates:
                try:
                    return datetime(year, month, day)
                except ValueError:
                    pass

        if len(digits) == 7:
            try:
                return datetime(
                    int(digits[3:7]),
                    int(digits[0]),
                    int(digits[1:3]),
                )
            except ValueError:
                pass

        if len(digits) == 6:
            month = int(digits[0:2])
            day = int(digits[2:4])
            two_digit_year = int(digits[4:6])
            year = 1900 + two_digit_year if two_digit_year > 30 else 2000 + two_digit_year
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

    formats = [
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%y",
        "%Y%m%d",
        "%m%d%Y",
        "%m%d%y",
    ]

    for date_format in formats:
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue

    return None


def add_clean_date_columns(
    df: pd.DataFrame,
    date_columns: List[str],
) -> pd.DataFrame:
    """Create MM/DD/YYYY clean date columns without removing records."""
    df = df.copy()
    current_year = datetime.now().year

    for column in date_columns:
        if column not in df.columns:
            print(f"Skipping missing date column: {column}")
            continue

        clean_column = f"{column}_CLEAN"
        output_values = []

        for raw_value in df[column]:
            parsed_date = _safe_parse_date(raw_value)

            if parsed_date is None:
                output_values.append(pd.NA)
                continue

            if column == "D_DOB":
                age = current_year - parsed_date.year
                if age < 4 or age > 25:
                    output_values.append(pd.NA)
                    continue

            output_values.append(parsed_date.strftime("%m/%d/%Y"))

        df[clean_column] = pd.Series(
            output_values,
            index=df.index,
            dtype="string",
        )

    return df


def place_all_clean_columns_next_to_originals(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Place each *_CLEAN column immediately after its base column."""
    df = df.copy()
    columns = list(df.columns)
    clean_columns = [
        column for column in columns if column.endswith("_CLEAN")
    ]

    for clean_column in clean_columns:
        original_column = clean_column[:-6]
        if original_column not in columns:
            continue
        columns.remove(clean_column)
        columns.insert(columns.index(original_column) + 1, clean_column)

    return df[columns]


# =========================================================
# LOAD WIDE COMBINED FILE
# =========================================================

if "combinedDf" in globals() and isinstance(combinedDf, pd.DataFrame):
    df_wide = _normalize_strings(combinedDf)
else:
    df_wide = pd.read_excel(
        COMBINED_FILE,
        dtype=str,
        engine="openpyxl",
    )
    df_wide = _normalize_strings(df_wide)

# Normalize an upstream FLAGGED_REASON name when supplied.
if "FLAGGED_REASON" in df_wide.columns:
    if "FLAG_REASON" not in df_wide.columns:
        df_wide = df_wide.rename(columns={"FLAGGED_REASON": "FLAG_REASON"})
    else:
        df_wide = merge_flag_reason_values(
            df_wide,
            source_column="FLAGGED_REASON",
            target_column="FLAG_REASON",
        )
        df_wide = df_wide.drop(columns=["FLAGGED_REASON"], errors="ignore")

# Keep only flags that should be carried into the retained long file.
# non-numeric_ss is deliberately excluded and recalculated later.
if "FLAG_REASON" in df_wide.columns:
    df_wide = filter_flag_reasons(
        df_wide,
        allowed_reasons=UPSTREAM_FLAGS_TO_RETAIN,
        flag_column="FLAG_REASON",
    )

# Prevent AGENCYCODE.1 from entering the pivot.
df_wide = drop_unwanted_duplicate_columns(df_wide)

print(f"Wide combined-file rows loaded: {len(df_wide):,}")


# =========================================================
# MARK DUPLICATES, PIVOT, AND PREFIX
# =========================================================

df_wide, exact_duplicate_comparison_columns = (
    mark_exact_duplicates_in_combined_file(df_wide)
)

df_long = pivot_scores_long_no_impute(df_wide).reset_index(drop=True)
print(f"Long-format rows created before removals: {len(df_long):,}")

df_long = rename_columns_upper_with_prefix(df_long)



#==========================================================
# iF EXISTS, CONCATENATE ADDENDUM.
# to be used when files are provided in long format
# or are manually created by NWEA analyst in long format.
#===========================================================


addendum_file = DATA_ROOT / "df_long_addendum.parquet"

if addendum_file.exists():

    df_long_addendum = pd.read_parquet(
        addendum_file
    )

    df_long = pd.concat(
        [
            df_long,
            df_long_addendum
        ],
        ignore_index=True,
        sort=False
    )

    print(
        f"Appended {len(df_long_addendum):,} "
        "records from df_long_addendum.parquet"
    )

else:

    print(
        "df_long_addendum.parquet not found. "
        "Using df_long only."
    )



# =========================================================
# INITIALIZE FLAG AND REMOVAL FIELDS
# =========================================================

df_long["FLAG_REASON"] = pd.Series(
    pd.NA,
    index=df_long.index,
    dtype="string",
)

for upstream_flag_column in ["D_FLAG_REASON", "D_FLAGGED_REASON"]:
    df_long = merge_flag_reason_values(
        df_long,
        source_column=upstream_flag_column,
        target_column="FLAG_REASON",
    )

# Retain only approved upstream flags. This strips any upstream
# non-numeric_ss so that it can be recalculated on final retained rows.
df_long = filter_flag_reasons(
    df_long,
    allowed_reasons=UPSTREAM_FLAGS_TO_RETAIN,
    flag_column="FLAG_REASON",
)

df_long = df_long.drop(
    columns=["D_FLAG_REASON", "D_FLAGGED_REASON"],
    errors="ignore",
)

df_long["REMOVAL_REASON"] = pd.NA
df_long["REMOVE_RECORD"] = False


# =========================================================
# EXACT-DUPLICATE REMOVAL
# =========================================================

if "D_EXACT_DUPLICATE" in df_long.columns:
    exact_duplicate_mask = (
        df_long["D_EXACT_DUPLICATE"].fillna(False).astype(bool)
    )
else:
    exact_duplicate_mask = pd.Series(False, index=df_long.index, dtype=bool)

df_long = append_removal_reason(
    df=df_long,
    mask=exact_duplicate_mask,
    reason="exact_duplicate",
)


# =========================================================
# SCORE-PRESENCE VALIDATION
# =========================================================

(
    all_scores_invalid_mask,
    retained_invalid_score_mask,
) = get_score_validation_masks(
    df_long,
    score_columns=["D_SS", "D_PLCODE", "D_PLDESC", "D_PL"],
)

# This flag applies only to candidate retained records.
invalid_score_flag_mask = (
    retained_invalid_score_mask
    & ~df_long["REMOVE_RECORD"]
)

df_long = append_flag_reason(
    df=df_long,
    mask=invalid_score_flag_mask,
    reason="invalid_score",
)


# =========================================================
# CREATE REMOVED RECORDS
# =========================================================

# All-invalid-score rows are excluded from removed_records by design.
save_in_removed_records_mask = (
    df_long["REMOVE_RECORD"]
    & ~all_scores_invalid_mask
)

removed_records = (
    df_long.loc[save_in_removed_records_mask]
    .copy()
    .reset_index(drop=True)
)

if "REMOVAL_REASON" in removed_records.columns:
    removal_reason = removed_records.pop("REMOVAL_REASON")
    removed_records.insert(0, "REMOVAL_REASON", removal_reason)

removed_records = removed_records.drop(
    columns=["D_EXACT_DUPLICATE", "REMOVE_RECORD"],
    errors="ignore",
)


# =========================================================
# CREATE RETAINED DF_LONG
# =========================================================

retain_long_mask = (
    ~df_long["REMOVE_RECORD"]
    & ~all_scores_invalid_mask
)

df_long = (
    df_long.loc[retain_long_mask]
    .copy()
    .reset_index(drop=True)
)

df_long = df_long.drop(
    columns=[
        "D_EXACT_DUPLICATE",
        "REMOVE_RECORD",
        "REMOVAL_REASON",
    ],
    errors="ignore",
)


# =========================================================
# CLEAN AND FLAG RETAINED RECORDS
# =========================================================

if "D_GRADE" in df_long.columns:
    print("\nOriginal grade value counts:")
    print(df_long["D_GRADE"].value_counts(dropna=False))

    df_long, cleaned_grades = add_clean_grade_column(df_long, "D_GRADE")

    print("\nOriginal and cleaned grade values:")
    print(
        df_long[["D_GRADE", "D_GRADE_CLEAN"]]
        .drop_duplicates()
        .sort_values(by=["D_GRADE"], na_position="last")
    )

    missing_grade_mask = df_long["D_GRADE_CLEAN"].isna()
    df_long = append_flag_reason(
        df=df_long,
        mask=missing_grade_mask,
        reason="missing_grade",
    )
else:
    missing_grade_mask = pd.Series(False, index=df_long.index, dtype=bool)
    print("D_GRADE was not found. Grade cleaning was skipped.")

# Integer cleaning. Do not convert date clean fields to Int64.
df_long = add_clean_int_columns(
    df_long,
    columns=[
        "D_LOCAL_STID",
        "D_STATE_STID",
        "D_AGENCYCODE",
        "D_SS",
    ],
)

# non-numeric_ss is calculated only on the final retained df_long.
if {"D_SS", "D_SS_CLEAN"}.issubset(df_long.columns):
    non_numeric_ss_mask = (
        df_long["D_SS"].apply(lambda value: not is_invalid_score_value(value))
        & df_long["D_SS_CLEAN"].isna()
    )
    df_long = append_flag_reason(
        df=df_long,
        mask=non_numeric_ss_mask,
        reason="non-numeric_ss",
    )
else:
    non_numeric_ss_mask = pd.Series(False, index=df_long.index, dtype=bool)
    print(
        "D_SS or D_SS_CLEAN was not found. "
        "The non-numeric_ss check was skipped."
    )

# Date cleaning. These remain string dates, not nullable integers.
df_long = add_clean_date_columns(
    df_long,
    date_columns=["D_TESTDATE", "D_DOB"],
)

df_long = place_all_clean_columns_next_to_originals(df_long)

# Move FLAG_REASON to the first column after all flags are finalized.
if "FLAG_REASON" in df_long.columns:
    flag_reason = df_long.pop("FLAG_REASON")
    df_long.insert(0, "FLAG_REASON", flag_reason)


# =========================================================
# FINAL COLUMN CLEANUP
# =========================================================

for dataframe_name in ["df_wide", "df_long", "removed_records"]:
    dataframe = globals()[dataframe_name]
    dataframe = drop_legacy_and_unwanted_columns(dataframe)
    dataframe = drop_unwanted_duplicate_columns(dataframe)
    globals()[dataframe_name] = dataframe

# The internal duplicate marker is not saved in df_wide.
df_wide = df_wide.drop(columns=["EXACT_DUPLICATE"], errors="ignore")


# =========================================================
# OUTPUT VALIDATION
# =========================================================

for dataframe_name, dataframe in [
    ("df_wide", df_wide),
    ("df_long", df_long),
    ("removed_records", removed_records),
]:
    unexpected_columns = [
        column
        for column in dataframe.columns
        if str(column).strip().upper() in {
            "AGENCYCODE.1",
            "D_AGENCYCODE.1",
        }
    ]
    if unexpected_columns:
        raise ValueError(
            f"{dataframe_name} still contains unwanted columns: "
            f"{unexpected_columns}"
        )

if "FLAG_REASON" not in df_long.columns:
    raise ValueError("FLAG_REASON is missing from df_long.")

# Validate non-numeric_ss placement and definition.
non_numeric_ss_flag_mask = (
    df_long["FLAG_REASON"]
    .astype("string")
    .fillna("")
    .str.split("|", regex=False)
    .apply(lambda reasons: "non-numeric_ss" in reasons)
)

invalid_non_numeric_ss_flag = (
    non_numeric_ss_flag_mask
    & (
        df_long["D_SS_CLEAN"].notna()
        | df_long["D_SS"].apply(is_invalid_score_value)
    )
) if {"D_SS", "D_SS_CLEAN"}.issubset(df_long.columns) else pd.Series(
    False,
    index=df_long.index,
    dtype=bool,
)

if invalid_non_numeric_ss_flag.any():
    raise ValueError(
        "One or more non-numeric_ss flags were applied incorrectly."
    )


# =========================================================
# SANITIZE PARQUET OUTPUTS
# =========================================================

df_wide = sanitize_object_columns(df_wide)
df_long = sanitize_object_columns(df_long)
removed_records = sanitize_object_columns(removed_records)


# =========================================================
# QA SUMMARY
# =========================================================

print("\n" + "=" * 60)
print("PIVOT, FLAG, AND REMOVAL SUMMARY")
print("=" * 60)
print(
    "Long records marked exact duplicate: "
    f"{int(exact_duplicate_mask.sum()):,}"
)
print(
    "All-invalid score records excluded: "
    f"{int(all_scores_invalid_mask.sum()):,}"
)
print(
    "Retained records flagged invalid_score: "
    f"{int(invalid_score_flag_mask.sum()):,}"
)
print(
    "Retained records flagged missing_grade: "
    f"{int(missing_grade_mask.sum()):,}"
)
print(
    "Retained records flagged non-numeric_ss: "
    f"{int(non_numeric_ss_flag_mask.sum()):,}"
)
print(
    "Records written to removed_records: "
    f"{len(removed_records):,}"
)
print(
    "Total long records retained: "
    f"{len(df_long):,}"
)

if "FLAG_REASON" in df_long.columns:
    print("\nRetained-record FLAG_REASON combinations:")
    print(df_long["FLAG_REASON"].value_counts(dropna=False))

if not removed_records.empty and "REMOVAL_REASON" in removed_records.columns:
    print("\nRemoval reason counts:")
    print(removed_records["REMOVAL_REASON"].value_counts(dropna=False))


# =========================================================
# SAVE OUTPUT
# =========================================================

df_wide.to_parquet(
    DATA_ROOT / "df_wide.parquet",
    index=False,
)

df_long.to_parquet(
    DATA_ROOT / "df_long.parquet",
    index=False,
)

removed_records.to_parquet(
    DATA_ROOT / "removed_records.parquet",
    index=False,
)

print("\nOutput files written:")
print(DATA_ROOT / "df_wide.parquet")
print(DATA_ROOT / "df_long.parquet")
print(DATA_ROOT / "removed_records.parquet")
