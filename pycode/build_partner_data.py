# -*- coding: utf-8 -*-
"""
Build partner data for a linking study.

Combines:
    1. Partner working-file consolidation
    2. Wide-to-long subject transformation
    3. Grade, integer, and date cleaning
    4. Settings merge
    5. Record validation and flagging
    6. Parquet output creation

@author: Chris.Wells
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional
import re
import sys

import numpy as np
import pandas as pd


# Spyder sometimes gets screwy with the working directory.
ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


from pycode.settings import *  # noqa: F401,F403,E402


# =============================================================================
# GENERAL HELPERS
# =============================================================================

def normalize_strings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize missing values, force values to pandas string dtype,
    and uppercase column names.
    """
    df = df.copy()

    # Convert NumPy NaN to pandas NA.
    df = df.where(pd.notna(df), pd.NA)

    # Convert blank or whitespace-only strings to NA.
    df = df.replace(r"^\s*$", pd.NA, regex=True)

    # Retain fields as text during partner-data ingestion.
    df = df.astype("string")

    # Standardize column names.
    df.columns = [
        str(column).strip().upper()
        for column in df.columns
    ]

    return df


def read_as_excel(path: Path) -> pd.DataFrame:
    """
    Read the first Excel worksheet with all fields treated as text.
    """
    df = pd.read_excel(
        path,
        sheet_name=0,
        dtype=str,
        engine="openpyxl",
    )

    return normalize_strings(df)


def read_as_csv(path: Path) -> pd.DataFrame:
    """
    Read a CSV using a sequence of likely encodings.
    """
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            df = pd.read_csv(
                path,
                dtype=str,
                encoding=encoding,
            )

            return normalize_strings(df)

        except UnicodeDecodeError:
            continue

    # Final fallback replaces invalid characters.
    df = pd.read_csv(
        path,
        dtype=str,
        encoding_errors="replace",
    )

    return normalize_strings(df)


def read_any_file_loose(path: Path) -> pd.DataFrame:
    """
    Attempt to read a file as Excel or CSV regardless of extension.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        readers = (read_as_csv, read_as_excel)
    else:
        readers = (read_as_excel, read_as_csv)

    last_error = None

    for reader in readers:
        try:
            return reader(path)

        except Exception as error:
            last_error = error

    raise last_error


def extract_agency_code(filename: str) -> Optional[str]:
    """
    Extract trailing digits from a filename.

    The digits must be preceded by:
        - start of filename
        - space
        - underscore
        - hyphen

    Examples:
        district_12345.xlsx -> 12345
        district-12345.csv  -> 12345
        district 12345.xlsx -> 12345
    """
    match = re.search(
        r"(?:^|[ _-])(\d+)(?=\.(xlsx|csv)$)",
        filename,
        flags=re.IGNORECASE,
    )

    return match.group(1) if match else None


def get_template_columns(template_path: Path) -> List[str]:
    """
    Read template headers without loading template data.
    """
    template_path = Path(template_path)

    if template_path.suffix.lower() == ".csv":
        template = pd.read_csv(
            template_path,
            dtype=str,
            nrows=0,
        )

    else:
        template = pd.read_excel(
            template_path,
            dtype=str,
            nrows=0,
            engine="openpyxl",
        )

    return [
        str(column).strip().upper()
        for column in template.columns
    ]


def sanitize_object_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert object-column values to Parquet-safe scalar strings.

    List-valued fields, such as SETTINGS_GRADE_LIST, are converted
    to their string representations.
    """
    df = df.copy()

    def sanitize_value(value):

        if value is None:
            return None

        if isinstance(value, float) and pd.isna(value):
            return None

        if isinstance(value, (list, tuple, set, np.ndarray)):
            return str(list(value))

        return str(value).strip()

    for column in df.columns:
        if df[column].dtype == "object":
            df[column] = df[column].apply(sanitize_value)

    return df


# =============================================================================
# STAGE 1: COMBINE PARTNER WORKING FILES
# =============================================================================

def combine_working_files_using_template(
    working_dir: Path,
    template_path: Path,
    combined_file: Path,
    sheet_name: str = "combined",
) -> pd.DataFrame:
    """
    Combine valid partner files using template headers assigned by position.

    Files are skipped if:
        - they cannot be read as Excel or CSV
        - their column count does not match the template

    Metadata added:
        FILENAMEFROMDISTRICT
        AGENCYCODE
    """
    working_dir = Path(working_dir)
    template_path = Path(template_path)
    combined_file = Path(combined_file)

    combined_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    template_columns = get_template_columns(template_path)
    template_column_count = len(template_columns)

    files = sorted(
        path
        for path in working_dir.iterdir()
        if path.is_file()
    )

    valid_frames = []
    skipped_files = []

    print(f"Template columns: {template_column_count}")

    for file_path in files:

        try:
            df = read_any_file_loose(file_path)

        except Exception as error:
            skipped_files.append(
                (
                    file_path.name,
                    "UNREADABLE",
                    str(error),
                )
            )

            print(
                f"[SKIP] Unreadable as Excel/CSV: "
                f"{file_path.name} ({error})"
            )

            continue

        # Remove metadata if a previously processed file is encountered.
        metadata_columns = [
            column
            for column in df.columns
            if column in (
                "FILENAMEFROMDISTRICT",
                "AGENCY_CODE",
                "AGENCYCODE",
            )
        ]

        if metadata_columns:
            df = df.drop(
                columns=metadata_columns,
                errors="ignore",
            )

        if df.shape[1] != template_column_count:
            detail = (
                f"expected {template_column_count}, "
                f"got {df.shape[1]}"
            )

            skipped_files.append(
                (
                    file_path.name,
                    "COL_MISMATCH",
                    detail,
                )
            )

            print(
                f"[SKIP] Column mismatch: "
                f"{file_path.name} ({detail})"
            )

            continue

        df = df.copy()

        # Apply template headers by position.
        df.columns = template_columns

        # Add source-file metadata.
        df["FILENAMEFROMDISTRICT"] = file_path.name

        agency_code = extract_agency_code(file_path.name)

        df["AGENCYCODE"] = pd.Series(
            agency_code,
            index=df.index,
            dtype="string",
        )

        valid_frames.append(df)

        print(
            f"[OK] {file_path.name} "
            f"rows={len(df):,} "
            f"cols={df.shape[1]}"
        )

    output_columns = (
        template_columns
        + ["FILENAMEFROMDISTRICT", "AGENCYCODE"]
    )

    if valid_frames:
        combined_df = pd.concat(
            valid_frames,
            ignore_index=True,
            sort=False,
        )

        combined_df = combined_df[output_columns]

    else:
        combined_df = pd.DataFrame(
            columns=output_columns
        )

    with pd.ExcelWriter(
        combined_file,
        engine="openpyxl",
    ) as writer:

        combined_df.to_excel(
            writer,
            index=False,
            sheet_name=sheet_name,
            na_rep="",
        )

        if skipped_files:
            skipped_df = pd.DataFrame(
                skipped_files,
                columns=["FILE", "REASON", "DETAIL"],
            )

            skipped_df.to_excel(
                writer,
                index=False,
                sheet_name="SKIPPED_FILES",
                na_rep="",
            )

    print(f"[DONE] Wrote combined file: {combined_file}")
    print(
        f"       Files combined: {len(valid_frames)} | "
        f"Files skipped: {len(skipped_files)}"
    )
    print(
        f"       Combined rows: {len(combined_df):,} | "
        f"Combined cols: {combined_df.shape[1]}"
    )

    return combined_df


# =============================================================================
# STAGE 2: WIDE-TO-LONG TRANSFORMATION
# =============================================================================

def pivot_scores_long_no_impute(
    combined_df: pd.DataFrame,
    suffixes: List[str],
    drop_rows_missing_ss: bool = False,
    drop_rows_all_scores_missing: bool = True,
) -> pd.DataFrame:
    """
    Convert subject-specific wide columns to long format.

    Subject columns are identified using the final underscore-delimited
    suffix. For example:

        MATHEMATICS_SS
        MATHEMATICS_PLCODE
        MATHEMATICS_PLDESC
        MATHEMATICS_TESTDATE

    becomes:

        SUBJECT = MATHEMATICS
        SS
        PLCODE
        PLDESC
        TESTDATE
    """
    df = combined_df.copy()

    suffixes = [
        str(suffix).upper()
        for suffix in suffixes
    ]

    suffix_expression = "|".join(
        re.escape(suffix)
        for suffix in suffixes
    )

    suffix_pattern = re.compile(
        rf"^(?P<subject>.+)_(?P<suffix>{suffix_expression})$",
        flags=re.IGNORECASE,
    )

    score_columns = []
    subjects = []
    column_mapping = {}

    for column in df.columns:

        match = suffix_pattern.match(str(column))

        if not match:
            continue

        subject = match.group("subject")
        suffix = match.group("suffix").upper()

        score_columns.append(column)
        subjects.append(subject)

        column_mapping[column] = (
            subject,
            suffix,
        )

    subjects = sorted(
        pd.unique(subjects)
    )

    non_subject_fields = [
        column
        for column in df.columns
        if column not in score_columns
    ]

    long_parts = []

    for subject in subjects:

        subject_columns = [
            column
            for column in score_columns
            if column_mapping[column][0] == subject
        ]

        temp = df[
            non_subject_fields + subject_columns
        ].copy()

        temp["SUBJECT"] = subject

        rename_map = {
            column: column_mapping[column][1]
            for column in subject_columns
        }

        temp = temp.rename(columns=rename_map)

        for suffix in suffixes:
            if suffix not in temp.columns:
                temp[suffix] = pd.NA

        temp = temp[
            non_subject_fields
            + ["SUBJECT"]
            + suffixes
        ]

        long_parts.append(temp)

    if not long_parts:

        output = df[non_subject_fields].copy()
        output["SUBJECT"] = pd.NA

        for suffix in suffixes:
            output[suffix] = pd.NA

        return output

    long_df = pd.concat(
        long_parts,
        ignore_index=True,
    )

    long_df[suffixes] = long_df[
        suffixes
    ].replace(
        r"^\s*$",
        pd.NA,
        regex=True,
    )

    if drop_rows_all_scores_missing:
        long_df = long_df.dropna(
            subset=suffixes,
            how="all",
        )

    if drop_rows_missing_ss and "SS" in long_df.columns:
        long_df = long_df.dropna(
            subset=["SS"]
        )

    return long_df


def rename_columns_upper_with_prefix(
    df: pd.DataFrame,
    prefix: str = "D_",
) -> pd.DataFrame:
    """
    Uppercase all column names and prepend a source prefix.
    """
    df = df.copy()

    df.columns = [
        f"{prefix}{str(column).strip().upper()}"
        for column in df.columns
    ]

    return df


# =============================================================================
# STAGE 3: FIELD CLEANING
# =============================================================================

GRADE_MAP = {
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
    """
    Normalize grade labels for comparison.
    """
    return re.sub(
        r"\s+",
        "",
        str(value).strip().upper(),
    )


REVERSE_GRADE_MAP = {
    normalize_grade_text(variant): grade
    for grade, variants in GRADE_MAP.items()
    for variant in variants
}


def add_clean_grade_column(
    df: pd.DataFrame,
    column: str,
) -> pd.DataFrame:
    """
    Add an Int64 grade-cleaning column.
    """
    df = df.copy()

    clean_column = f"{column}_CLEAN"

    def clean_grade(raw_value):

        if pd.isna(raw_value):
            return pd.NA

        raw_string = str(raw_value).strip()

        try:
            numeric_value = float(raw_string)

            if numeric_value.is_integer():
                numeric_value = int(numeric_value)

                if numeric_value in GRADE_MAP:
                    return numeric_value

        except (ValueError, TypeError):
            pass

        normalized = normalize_grade_text(raw_value)

        return REVERSE_GRADE_MAP.get(
            normalized,
            pd.NA,
        )

    df[clean_column] = (
        df[column]
        .apply(clean_grade)
        .astype("Int64")
    )

    return df


# def add_clean_int_columns(
#     df: pd.DataFrame,
#     columns: List[str],
# ) -> pd.DataFrame:
#     """
#     Add *_CLEAN Int64 columns for numeric fields.
#     """
#     df = df.copy()

#     for column in columns:

#         if column not in df.columns:
#             continue

#         clean_column = f"{column}_CLEAN"

#         values = df[column].replace(
#             r"^\s*$",
#             pd.NA,
#             regex=True,
#         )

#         df[clean_column] = pd.to_numeric(
#             values,
#             errors="coerce",
#         ).astype("Int64")

#     return df

# agency_df = df_long.loc[:, df_long.columns == "D_AGENCYCODE"]

def add_clean_int_columns(
    df: pd.DataFrame,
    columns: List[str],
) -> pd.DataFrame:

    df = df.copy()

    for column in columns:

        print("\n----------------------")
        print("COLUMN:", column)

        if column not in df.columns:
            print("NOT FOUND")
            continue

        print(
            "MATCH COUNT:",
            (df.columns == column).sum()
        )

        values = df[column]

        print(
            "TYPE:",
            type(values)
        )

        print(
            "SHAPE:",
            getattr(values, "shape", None)
        )

        clean_column = f"{column}_CLEAN"

        values = values.replace(
            r"^\s*$",
            pd.NA,
            regex=True,
        )

        df[clean_column] = pd.to_numeric(
            values,
            errors="coerce",
        ).astype("Int64")

    return df


def parse_term_to_year(term) -> Optional[int]:
    """
    Extract the first four-digit year from a term value.
    """
    if term is None or pd.isna(term):
        return None

    match = re.search(
        r"(\d{4})",
        str(term),
    )

    return int(match.group(1)) if match else None


def safe_parse_date(raw_value) -> Optional[datetime]:
    """
    Parse common district date representations.
    """
    if raw_value is None or pd.isna(raw_value):
        return None

    value = str(raw_value).strip()

    # Remove trailing time values.
    value = re.sub(
        r"\s+\d{1,2}:\d{2}(:\d{2})?$",
        "",
        value,
    )

    if re.fullmatch(r"\d+", value):

        # MMDDYYYY or YYYYMMDD
        if len(value) == 8:

            candidates = [
                (
                    int(value[4:8]),
                    int(value[0:2]),
                    int(value[2:4]),
                ),
                (
                    int(value[0:4]),
                    int(value[4:6]),
                    int(value[6:8]),
                ),
            ]

            for year, month, day in candidates:
                try:
                    return datetime(
                        year,
                        month,
                        day,
                    )

                except ValueError:
                    pass

        # MDDYYYY
        elif len(value) == 7:

            try:
                return datetime(
                    int(value[3:7]),
                    int(value[0]),
                    int(value[1:3]),
                )

            except ValueError:
                pass

        # MMDDYY
        elif len(value) == 6:

            month = int(value[0:2])
            day = int(value[2:4])
            two_digit_year = int(value[4:6])

            year = (
                1900 + two_digit_year
                if two_digit_year > 30
                else 2000 + two_digit_year
            )

            try:
                return datetime(
                    year,
                    month,
                    day,
                )

            except ValueError:
                pass

    formats = (
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%y",
        "%Y%m%d",
        "%m%d%Y",
        "%m%d%y",
    )

    for date_format in formats:
        try:
            return datetime.strptime(
                value,
                date_format,
            )

        except ValueError:
            continue

    return None


def add_clean_date_columns(
    df: pd.DataFrame,
    date_columns: List[str],
) -> pd.DataFrame:
    """
    Add standardized MM/DD/YYYY date columns.

    DOB values are nulled when the derived age is outside 4 through 25.
    """
    df = df.copy()

    current_year = datetime.now().year

    for column in date_columns:

        if column not in df.columns:
            continue

        output = []

        for raw_value in df[column]:

            parsed_date = safe_parse_date(raw_value)

            if parsed_date is None:
                output.append(pd.NA)
                continue

            if column == "D_DOB":

                age = current_year - parsed_date.year

                if age < 4 or age > 25:
                    output.append(pd.NA)
                    continue

            output.append(
                parsed_date.strftime("%m/%d/%Y")
            )

        df[f"{column}_CLEAN"] = pd.Series(
            output,
            index=df.index,
            dtype="string",
        )

    return df


def place_all_clean_columns_next_to_originals(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Place each *_CLEAN column immediately after its source column.
    """
    df = df.copy()
    columns = list(df.columns)

    clean_columns = [
        column
        for column in columns
        if column.endswith("_CLEAN")
    ]

    for clean_column in clean_columns:

        original_column = clean_column[:-6]

        if original_column not in columns:
            continue

        columns.remove(clean_column)

        insertion_position = (
            columns.index(original_column) + 1
        )

        columns.insert(
            insertion_position,
            clean_column,
        )

    return df[columns]


# =============================================================================
# STAGE 4: SETTINGS AND VALIDATION HELPERS
# =============================================================================

def append_flag_reason(
    df: pd.DataFrame,
    mask,
    reason: str,
) -> pd.DataFrame:
    """
    Append a pipe-delimited reason to FLAG_REASON.
    """
    df = df.copy()

    mask = pd.Series(
        mask,
        index=df.index,
    ).fillna(False).astype(bool)

    current = df.loc[
        mask,
        "FLAG_REASON",
    ]

    df.loc[
        mask,
        "FLAG_REASON",
    ] = np.where(
        current.isna(),
        reason,
        current.astype(str) + "|" + reason,
    )

    return df


def parse_study_grades(raw_value) -> List[int]:
    """
    Parse study-grade strings such as:

        3,4,5
        3-5
        K,1,2
        GRADE 3; GRADE 4
    """
    if raw_value is None or pd.isna(raw_value):
        return []

    value = str(raw_value).upper().strip()

    tokens = re.split(
        r"[,;]+|\s+(?!\d*\s*-)",
        value,
    )

    output = []

    for token in tokens:

        token = token.strip()

        if not token:
            continue

        compact_token = normalize_grade_text(token)

        range_match = re.fullmatch(
            r"(.+?)-(.+)",
            compact_token,
        )

        if range_match:

            low_token, high_token = range_match.groups()

            low_grade = REVERSE_GRADE_MAP.get(low_token)
            high_grade = REVERSE_GRADE_MAP.get(high_token)

            if low_grade is None and low_token.isdigit():
                low_grade = int(low_token)

            if high_grade is None and high_token.isdigit():
                high_grade = int(high_token)

            if low_grade is not None and high_grade is not None:
                output.extend(
                    range(low_grade, high_grade + 1)
                )

            continue

        grade = REVERSE_GRADE_MAP.get(compact_token)

        if grade is None and compact_token.isdigit():
            grade = int(compact_token)

        if grade in GRADE_MAP:
            output.append(grade)

    return sorted(set(output))


def is_incorrect_term(
    district_term,
    settings_term,
) -> bool:
    """
    Determine whether the district term conflicts with the configured term.

    Flags:
        - explicit Fall terms
        - explicit Summer terms
        - explicit Winter terms
        - terms containing a conflicting year

    Does not flag:
        - blanks
        - unrecognized term text
        - Spring without a year
    """
    if pd.isna(district_term) or pd.isna(settings_term):
        return False

    district_term = str(
        district_term
    ).upper().strip()

    settings_match = re.match(
        r"^(\d{4})",
        str(settings_term).strip(),
    )

    if not settings_match:
        return False

    study_year = int(settings_match.group(1))

    non_spring_patterns = (
        r"\bFALL\b",
        r"\bAUTUMN\b",
        r"\bFA\b",
        r"\bF\d{2}\b",
        r"\bSUMMER\b",
        r"\bSUM\b",
        r"\bSU\b",
        r"\bWINTER\b",
        r"\bWIN\b",
        r"\bWI\b",
        r"\bW\d{2}\b",
    )

    if any(
        re.search(pattern, district_term)
        for pattern in non_spring_patterns
    ):
        return True

    years_found = {
        int(year)
        for year in re.findall(
            r"20\d{2}",
            district_term,
        )
    }

    short_years = re.findall(
        r"(?<!\d)(\d{2})(?!\d)",
        district_term,
    )

    years_found.update(
        2000 + int(year)
        for year in short_years
        if 0 <= int(year) <= 50
    )

    return bool(
        years_found
        and study_year not in years_found
        and study_year - 1 not in years_found
    )


def is_test_date_out_of_range(
    test_date,
    settings_term,
) -> bool:
    """
    Flag test dates outside February 1 through June 30
    of the configured study year.
    """
    if pd.isna(test_date) or pd.isna(settings_term):
        return False

    parsed_date = pd.to_datetime(
        test_date,
        errors="coerce",
    )

    if pd.isna(parsed_date):
        return False

    settings_match = re.match(
        r"^(\d{4})",
        str(settings_term).strip(),
    )

    if not settings_match:
        return False

    study_year = int(settings_match.group(1))

    valid_start = pd.Timestamp(
        study_year,
        2,
        1,
    )

    valid_end = pd.Timestamp(
        study_year,
        6,
        30,
    )

    return (
        parsed_date < valid_start
        or parsed_date > valid_end
    )


# =============================================================================
# STAGE 5: CLEAN AND VALIDATE LONG DATA
# =============================================================================

def clean_and_validate_long_data(
    combined_df: pd.DataFrame,
    settings_df: pd.DataFrame,
    suffixes: List[str],
) -> dict:
    """
    Pivot, clean, merge settings, flag invalid records, and build outputs.
    """
    df_wide = normalize_strings(combined_df)

    df_long = pivot_scores_long_no_impute(
        combined_df=df_wide,
        suffixes=suffixes,
        drop_rows_missing_ss=False,
        drop_rows_all_scores_missing=False,
    )

    # Retain a subject record when at least one principal score or
    # performance-level field is populated.
    populated_score_columns = [
        column
        for column in (
            "SS",
            "PLCODE",
            "PLDESC",
            "PL",
        )
        if column in df_long.columns
    ]

    if populated_score_columns:

        populated_mask = df_long[
            populated_score_columns
        ].notna().any(axis=1)

        df_long = (
            df_long.loc[populated_mask]
            .reset_index(drop=True)
        )

    else:
        df_long = df_long.iloc[0:0].copy()

    # Prefix district fields.
    df_long = rename_columns_upper_with_prefix(
        df_long,
        prefix="D_",
    )

    required_long_columns = [
        "D_GRADE",
        "D_SUBJECT",
        "D_TERM",
        "D_SS",
    ]

    missing_required_columns = [
        column
        for column in required_long_columns
        if column not in df_long.columns
    ]

    if missing_required_columns:
        raise KeyError(
            "Required long-format columns are missing: "
            f"{missing_required_columns}"
        )

    # Grade cleaning.
    df_long = add_clean_grade_column(
        df_long,
        "D_GRADE",
    )


    # temp QA
    agency_df = df_long.loc[:, df_long.columns == "D_AGENCYCODE"]

    print(type(agency_df))
    print(agency_df.shape)
    
    # Numeric cleaning.
    df_long = add_clean_int_columns(
        df_long,
        columns=[
            "D_LOCAL_STID",
            "D_STATE_STID",
            "D_AGENCYCODE",
            "D_SS",
        ],
    )

    # Date cleaning.
    df_long = add_clean_date_columns(
        df_long,
        date_columns=[
            "D_TESTDATE",
            "D_DOB",
        ],
    )

    df_long = place_all_clean_columns_next_to_originals(
        df_long
    )

    # -------------------------------------------------------------------------
    # Prepare settings
    # -------------------------------------------------------------------------

    settings_prefixed = settings_df.copy()

    settings_prefixed.columns = [
        (
            str(column)
            if str(column).startswith("SETTINGS_")
            else f"SETTINGS_{column}"
        )
        for column in settings_prefixed.columns
    ]

    required_settings_columns = [
        "SETTINGS_D_SUBJECT",
        "SETTINGS_STUDY_GRADES",
        "SETTINGS_TERM",
    ]

    missing_settings_columns = [
        column
        for column in required_settings_columns
        if column not in settings_prefixed.columns
    ]

    if missing_settings_columns:
        raise KeyError(
            "Required settings columns are missing: "
            f"{missing_settings_columns}"
        )

    settings_prefixed["SETTINGS_GRADE_LIST"] = (
        settings_prefixed[
            "SETTINGS_STUDY_GRADES"
        ].apply(parse_study_grades)
    )

    # -------------------------------------------------------------------------
    # Merge district data with settings
    # -------------------------------------------------------------------------

    merged = df_long.merge(
        settings_prefixed,
        left_on="D_SUBJECT",
        right_on="SETTINGS_D_SUBJECT",
        how="left",
        indicator=True,
    )

    merged_dropped_subjects = (
        merged.loc[
            merged["_merge"] == "left_only"
        ]
        .drop(columns=["_merge"])
        .reset_index(drop=True)
    )

    merged_inner = (
        merged.loc[
            merged["_merge"] == "both"
        ]
        .drop(columns=["_merge"])
        .reset_index(drop=True)
    )

    merged_inner["FLAG_REASON"] = pd.NA

    # -------------------------------------------------------------------------
    # Flag missing grade
    # -------------------------------------------------------------------------

    merged_inner = append_flag_reason(
        merged_inner,
        merged_inner["D_GRADE_CLEAN"].isna(),
        "missing_grade",
    )

    # -------------------------------------------------------------------------
    # Build subject-level grade eligibility
    # -------------------------------------------------------------------------

    allowed_grades_by_subject = (
        settings_prefixed
        .groupby("SETTINGS_D_SUBJECT")[
            "SETTINGS_GRADE_LIST"
        ]
        .apply(
            lambda grade_lists: {
                int(grade)
                for grade_list in grade_lists.dropna()
                for grade in grade_list
            }
        )
        .to_dict()
    )

    merged_inner["GRADE_ALLOWED_ANY_STUDY"] = [
        (
            pd.notna(subject)
            and pd.notna(grade)
            and subject in allowed_grades_by_subject
            and int(grade)
            in allowed_grades_by_subject[subject]
        )
        for subject, grade in zip(
            merged_inner["D_SUBJECT"],
            merged_inner["D_GRADE_CLEAN"],
        )
    ]

    merged_inner = append_flag_reason(
        merged_inner,
        (
            merged_inner["D_GRADE_CLEAN"].notna()
            & ~merged_inner["GRADE_ALLOWED_ANY_STUDY"]
        ),
        "grade_not_in_study",
    )

    # -------------------------------------------------------------------------
    # Flag non-numeric scale scores
    # -------------------------------------------------------------------------

    if "D_SS_CLEAN" in merged_inner.columns:

        non_numeric_ss_mask = (
            merged_inner["D_SS"].notna()
            & merged_inner[
                "D_SS"
            ].astype(str).str.strip().ne("")
            & merged_inner["D_SS_CLEAN"].isna()
        )

        merged_inner = append_flag_reason(
            merged_inner,
            non_numeric_ss_mask,
            "non_numeric_SS",
        )

    # -------------------------------------------------------------------------
    # Flag incorrect term
    # -------------------------------------------------------------------------

    incorrect_term_mask = [
        is_incorrect_term(
            district_term,
            settings_term,
        )
        for district_term, settings_term in zip(
            merged_inner["D_TERM"],
            merged_inner["SETTINGS_TERM"],
        )
    ]

    merged_inner = append_flag_reason(
        merged_inner,
        incorrect_term_mask,
        "incorrect_term",
    )

    # -------------------------------------------------------------------------
    # Flag test date outside the configured window
    # -------------------------------------------------------------------------

    if "D_TESTDATE_CLEAN" in merged_inner.columns:

        test_date_out_of_range_mask = [
            is_test_date_out_of_range(
                test_date,
                settings_term,
            )
            for test_date, settings_term in zip(
                merged_inner["D_TESTDATE_CLEAN"],
                merged_inner["SETTINGS_TERM"],
            )
        ]

        merged_inner = append_flag_reason(
            merged_inner,
            test_date_out_of_range_mask,
            "test_date_out_of_range",
        )

    # -------------------------------------------------------------------------
    # Create flagged-for-removal output
    # -------------------------------------------------------------------------

    flagged_for_removal = (
        merged_inner.loc[
            merged_inner["FLAG_REASON"].notna()
        ]
        .copy()
        .reset_index(drop=True)
    )

    if "FLAG_REASON" in flagged_for_removal.columns:

        flag_reason = flagged_for_removal.pop(
            "FLAG_REASON"
        )

        flagged_for_removal.insert(
            0,
            "FLAG_REASON",
            flag_reason,
        )

    # Remove flagged rows before study-specific grade filtering.
    unflagged = merged_inner.loc[
        merged_inner["FLAG_REASON"].isna()
    ].copy()

    # -------------------------------------------------------------------------
    # Filter to grades allowed for the specific settings row
    # -------------------------------------------------------------------------

    unflagged["GRADE_ALLOWED"] = unflagged.apply(
        lambda row: (
            pd.notna(row["D_GRADE_CLEAN"])
            and isinstance(
                row["SETTINGS_GRADE_LIST"],
                (list, tuple),
            )
            and row["D_GRADE_CLEAN"]
            in row["SETTINGS_GRADE_LIST"]
        ),
        axis=1,
    )

    merged_valid = (
        unflagged.loc[
            unflagged["GRADE_ALLOWED"]
        ]
        .copy()
        .reset_index(drop=True)
    )

    merged_valid["SETTINGS_STUDY_GRADES"] = (
        merged_valid[
            "SETTINGS_STUDY_GRADES"
        ].apply(
            lambda value: (
                None
                if pd.isna(value)
                else str(value).strip()
            )
        )
    )

    # Records that matched the subject but not the specific study-grade row.
    invalid_keep_columns = [
        "D_DISTRICTNAME",
        "D_SCHOOLNAME",
        "D_FILENAMEFROMDISTRICT",
        "D_SUBJECT",
        "SETTINGS_D_MAPGROWTH_TEST_NAME",
        "D_GRADE",
        "D_GRADE_CLEAN",
        "SETTINGS_STUDY_GRADES",
        "FLAG_REASON",
    ]

    merged_invalid = (
        unflagged.loc[
            ~unflagged["GRADE_ALLOWED"],
            [
                column
                for column in invalid_keep_columns
                if column in unflagged.columns
            ],
        ]
        .copy()
        .reset_index(drop=True)
    )

    final_long = merged_valid.drop(
        columns=[
            "SETTINGS_NOTES",
            "GRADE_ALLOWED_ANY_STUDY",
            "GRADE_ALLOWED",
        ],
        errors="ignore",
    )

    outputs = {
        "df_wide": sanitize_object_columns(
            df_wide
        ),
        "df_long": sanitize_object_columns(
            final_long
        ),
        "settings_prefixed": sanitize_object_columns(
            settings_prefixed
        ),
        "flagged_for_removal": sanitize_object_columns(
            flagged_for_removal
        ),
        "merged_invalid": sanitize_object_columns(
            merged_invalid
        ),
        "merged_dropped_subjects": sanitize_object_columns(
            merged_dropped_subjects
        ),
    }

    return outputs


# =============================================================================
# STAGE 6: SAVE OUTPUTS
# =============================================================================

def save_pipeline_outputs(
    outputs: dict,
    data_root: Path,
) -> None:
    """
    Save pipeline DataFrames as Parquet files.
    """
    data_root = Path(data_root)

    data_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_names = {
        "df_wide": "df_wide.parquet",
        "df_long": "df_long.parquet",
        "settings_prefixed": "settings_prefixed.parquet",
        "flagged_for_removal": "flagged_for_removal.parquet",
        "merged_invalid": "merged_invalid.parquet",
        "merged_dropped_subjects": (
            "merged_dropped_subjects.parquet"
        ),
    }

    for output_key, filename in output_names.items():

        output_path = data_root / filename

        outputs[output_key].to_parquet(
            output_path,
            index=False,
        )

        print(
            f"[DONE] Wrote {output_path} "
            f"rows={len(outputs[output_key]):,}"
        )


# =============================================================================
# COMPLETE BUILD
# =============================================================================

def build_partner_data() -> dict:
    """
    Run the complete partner-data build.

    Processing stages:
        1. Combine valid partner working files
        2. Create the wide combined workbook
        3. Pivot subject fields to long format
        4. Clean grade, numeric, and date fields
        5. Merge study settings
        6. Flag invalid records
        7. Save Parquet outputs
    """
    combined_df = combine_working_files_using_template(
        working_dir=WORKING_FILES,
        template_path=DATA_TEMPLATE,
        combined_file=COMBINED_FILE,
        sheet_name="combined",
    )

    configured_suffixes = [
        str(suffix).upper()
        for suffix in SUFFIXES
    ]
    
    outputs = combined_df

    # outputs = clean_and_validate_long_data(
    #     combined_df=combined_df,
    #     settings_df=settings_xl,
    #     suffixes=configured_suffixes,
    # )

    # save_pipeline_outputs(
    #     outputs=outputs,
    #     data_root=DATA_ROOT,
    # )

    return outputs


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    pipeline_outputs = build_partner_data()

    # Optional Spyder-friendly references.
    # df_wide = pipeline_outputs["df_wide"]
    # df_long = pipeline_outputs["df_long"]
    # settings_prefixed = pipeline_outputs["settings_prefixed"]
    # flagged_for_removal = pipeline_outputs["flagged_for_removal"]
    # merged_invalid = pipeline_outputs["merged_invalid"]
    # merged_dropped_subjects = pipeline_outputs[
    #     "merged_dropped_subjects"
    # ]