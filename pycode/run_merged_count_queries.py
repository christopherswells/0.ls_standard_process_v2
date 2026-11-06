# -*- coding: utf-8 -*-
"""
Run the merged linking-study count queries and write each result set to a
separate worksheet in the state/year merged-counts workbook.

Project conventions retained from the STUDYSAMPLE_QA runner:
- project settings are read from pycode.settings
- optional table-name settings override the standard state/year names
- execution uses common.ls_map_count_functions.query_snowflake_sqlalchemy

The SQL file contains four sections marked with:
    -- RESULT_SET: <worksheet name>

Output example:
    os.path.join(DATA_ROOT, STATE_ABR + DATA_YEAR + '_merged_counts.xlsx')
"""

from pathlib import Path
import os
import re
import sys

import pandas as pd


# -----------------------------------------------------------------------------
# Set the project root to Linking_Studies_Data_Prep_Code.
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from common.ls_map_count_functions import query_snowflake_sqlalchemy
from pycode.settings import *


SQL_PATH = ROOT / "common" / "py_sql"
SQL_SCRIPT = SQL_PATH / "merged_count_queries.sql"

RESULT_SET_PATTERN = re.compile(
    r"^\s*--\s*RESULT_SET:\s*(?P<sheet_name>.+?)\s*$",
    flags=re.MULTILINE,
)


# -----------------------------------------------------------------------------
# Settings and table-name helpers.
# -----------------------------------------------------------------------------
def _setting_or_default(setting_name, default_value):
    """Return a nonblank optional settings value, otherwise use the default."""
    value = globals().get(setting_name)
    if value is None or str(value).strip() == "":
        return default_value
    return str(value).strip()


def _first_setting_or_default(setting_names, default_value):
    """Return the first nonblank setting from a list of supported names."""
    for setting_name in setting_names:
        value = globals().get(setting_name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default_value


def _fully_qualified_table_name(table_name):
    """Qualify an unqualified table with the configured database and schema."""
    table_name = str(table_name).strip()
    if table_name.count(".") == 2:
        return table_name
    if table_name.count(".") == 1:
        return f"{DATABASE}.{table_name}"
    return f"{DATABASE}.{SCHEMA}.{table_name}"


def _snowflake_string_literal(value):
    """Return a safely quoted Snowflake string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def _render_query_variables(query, variables):
    """Render table-name variables as literals inside IDENTIFIER(...)."""
    rendered_query = query
    for variable_name, value in variables.items():
        token_pattern = re.compile(rf"\${re.escape(variable_name)}\b")
        rendered_query = token_pattern.sub(
            _snowflake_string_literal(value),
            rendered_query,
        )

    unresolved = sorted(set(re.findall(r"\$[A-Za-z_][A-Za-z0-9_]*", rendered_query)))
    if unresolved:
        raise ValueError(
            "Unresolved SQL template variables: " + ", ".join(unresolved)
        )

    return rendered_query.strip()


# -----------------------------------------------------------------------------
# SQL-section and result helpers.
# -----------------------------------------------------------------------------
def _load_result_queries(sql_script):
    """Read the marked SQL sections as ordered (worksheet, query) pairs."""
    sql_text = Path(sql_script).read_text(encoding="utf-8")
    matches = list(RESULT_SET_PATTERN.finditer(sql_text))

    if not matches:
        raise ValueError(
            f"No RESULT_SET sections were found in SQL script: {sql_script}"
        )

    result_queries = []
    seen_sheet_names = set()

    for index, match in enumerate(matches):
        sheet_name = match.group("sheet_name").strip()
        query_start = match.end()
        query_end = matches[index + 1].start() if index + 1 < len(matches) else len(sql_text)
        query = sql_text[query_start:query_end].strip()

        if not query:
            raise ValueError(f"The RESULT_SET section '{sheet_name}' has no SQL query.")
        if len(sheet_name) > 31:
            raise ValueError(
                f"Excel worksheet name exceeds 31 characters: {sheet_name}"
            )
        if sheet_name.casefold() in seen_sheet_names:
            raise ValueError(f"Duplicate Excel worksheet name: {sheet_name}")

        seen_sheet_names.add(sheet_name.casefold())
        result_queries.append((sheet_name, query))

    return result_queries


def _coerce_dataframe(query_result, sheet_name):
    """Normalize the shared query helper's returned tabular result."""
    if isinstance(query_result, pd.DataFrame):
        return query_result

    if isinstance(query_result, (list, tuple)):
        dataframes = [item for item in query_result if isinstance(item, pd.DataFrame)]
        if dataframes:
            return dataframes[-1]

    if query_result is None:
        raise RuntimeError(
            "The Snowflake query helper returned no tabular result for worksheet "
            f"'{sheet_name}'. Confirm that query_snowflake_sqlalchemy returns a "
            "pandas DataFrame for SELECT statements."
        )

    try:
        return pd.DataFrame(query_result)
    except Exception as exc:
        raise TypeError(
            f"Could not convert the query result for worksheet '{sheet_name}' "
            "to a pandas DataFrame."
        ) from exc


def _format_worksheet(writer, sheet_name, dataframe):
    """Apply light usability formatting without changing the query output."""
    worksheet = writer.sheets[sheet_name]
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    for column_index, column_name in enumerate(dataframe.columns, start=1):
        values = dataframe[column_name].astype(str) if not dataframe.empty else []
        max_value_length = max((len(value) for value in values), default=0)
        width = min(max(len(str(column_name)), max_value_length) + 2, 45)
        worksheet.column_dimensions[
            worksheet.cell(row=1, column=column_index).column_letter
        ].width = width


# -----------------------------------------------------------------------------
# Resolve state/year tables and workbook output.
# -----------------------------------------------------------------------------
state_code = str(STATE_ABR).strip().upper()
data_year = str(DATA_YEAR).strip()

merged_table = _setting_or_default(
    "merged_table_name",
    f"{state_code}{data_year}_STUDYSAMPLE_QA",
)
partner_table = _setting_or_default(
    "partner_table_name",
    f"{state_code}{data_year}_PARTNERDATA",
)
settings_table = _setting_or_default(
    "settings_table_name",
    f"{state_code}{data_year}_STUDY_SETTINGS",
)
map_growth_table = _first_setting_or_default(
    ("map_growth_table_name", "map_table_name"),
    f"{state_code}{data_year}_MAP_DATA",
)

variables = {
    "MERGED_TABLE_NAME": _fully_qualified_table_name(merged_table),
    "PARTNER_TABLE_NAME": _fully_qualified_table_name(partner_table),
    "MAP_GROWTH_TABLE_NAME": _fully_qualified_table_name(map_growth_table),
    "SETTINGS_TABLE_NAME": _fully_qualified_table_name(settings_table),
}

OUTMERGEDCOUNTS = os.path.join(
    DATA_ROOT,
    STATE_ABR + DATA_YEAR + "_merged_counts.xlsx",
)


# -----------------------------------------------------------------------------
# Execute each marked query and write its result to a separate Excel worksheet.
# -----------------------------------------------------------------------------
def main():
    result_queries = _load_result_queries(SQL_SCRIPT)
    output_path = Path(OUTMERGEDCOUNTS)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"SQL script: {SQL_SCRIPT}")
    print(f"Output workbook: {output_path}")
    print("Source tables:")
    for variable_name, table_name in variables.items():
        print(f"  {variable_name}: {table_name}")

    results = []
    for sheet_name, query in result_queries:
        print(f"Running query for worksheet: {sheet_name}")
        rendered_query = _render_query_variables(query, variables)
        query_result = query_snowflake_sqlalchemy(
            rendered_query,
            SNOWFLAKEUSER,
            ROLE,
            WAREHOUSE,
            DATABASE=DATABASE,
            SCHEMA=SCHEMA,
        )
        dataframe = _coerce_dataframe(query_result, sheet_name)
        print(f"  Rows returned: {len(dataframe):,}")
        results.append((sheet_name, dataframe))

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, dataframe in results:
            dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
            _format_worksheet(writer, sheet_name, dataframe)

    print(f"Created workbook: {output_path}")


if __name__ == "__main__":
    main()
