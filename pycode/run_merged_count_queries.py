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

Additional QA outputs:
- CORRELATION cells below 0.70 are highlighted in the workbook.
- Each low-correlation Study Grade Agency row produces an M_IRIT versus D_SS
  scatterplot in a sibling folder named 'low correlations'.
"""

from pathlib import Path
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from openpyxl.styles import Font, PatternFill


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

LOW_CORRELATION_THRESHOLD = 0.70
LOW_CORRELATION_SHEET = "Study Grade Agency"
LOW_CORRELATION_FOLDER_NAME = "low correlations"
LOW_CORRELATION_FILL = PatternFill(
    fill_type="solid",
    fgColor="FFC7CE",
)
LOW_CORRELATION_FONT = Font(color="9C0006")


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


def _find_column(dataframe, expected_name):
    """Return a DataFrame column by case-insensitive name."""
    expected_name = expected_name.casefold()
    for column_name in dataframe.columns:
        if str(column_name).casefold() == expected_name:
            return column_name
    raise KeyError(
        f"Required column '{expected_name}' was not found. "
        f"Available columns: {list(dataframe.columns)}"
    )


def _format_worksheet(writer, sheet_name, dataframe):
    """Apply usability formatting and flag low-correlation cells."""
    worksheet = writer.sheets[sheet_name]
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    for column_index, column_name in enumerate(dataframe.columns, start=1):
        values = dataframe[column_name].astype(str) if not dataframe.empty else []
        max_value_length = max((len(str(value)) for value in values), default=0)
        width = min(max(len(str(column_name)), max_value_length) + 2, 45)
        worksheet.column_dimensions[
            worksheet.cell(row=1, column=column_index).column_letter
        ].width = width

        if "correlation" in str(column_name).casefold():
            for row_index, value in enumerate(dataframe[column_name], start=2):
                numeric_value = pd.to_numeric(value, errors="coerce")
                if pd.notna(numeric_value) and numeric_value < LOW_CORRELATION_THRESHOLD:
                    cell = worksheet.cell(row=row_index, column=column_index)
                    cell.fill = LOW_CORRELATION_FILL
                    cell.font = LOW_CORRELATION_FONT
                    cell.number_format = "0.0000"


def _nullable_text_condition(sql_expression, value):
    """Build a null-safe text equality condition for one Snowflake value."""
    if pd.isna(value):
        return f"{sql_expression} IS NULL"
    return f"{sql_expression} = {_snowflake_string_literal(str(value).strip())}"


def _build_scatter_detail_query(row, columns):
    """Select the matched score pairs for one Study Grade Agency result row."""
    subject = row[columns["SETTINGS_D_SUBJECT"]]
    test_name = row[columns["SETTINGS_D_MAPGROWTH_TEST_NAME"]]
    grade = row[columns["GRADE"]]
    agency_code = row[columns["AGENCY_CODE"]]

    conditions = [
        _nullable_text_condition("mc.D_SUBJECT", subject),
        _nullable_text_condition("mc.M_TEST_NAME", test_name),
        _nullable_text_condition("TRIM(mc.D_GRADE::VARCHAR)", grade),
        _nullable_text_condition("TRIM(mc.D_AGENCYCODE::VARCHAR)", agency_code),
        "mc.MATCH_TYPE <> 'UNMATCHED'",
        "mc.M_IRIT IS NOT NULL",
        "mc.D_SS IS NOT NULL",
    ]

    return f"""
SELECT
    mc.M_IRIT,
    mc.D_SS
FROM IDENTIFIER({_snowflake_string_literal(variables['MERGED_TABLE_NAME'])}) mc
WHERE {' AND '.join(conditions)}
ORDER BY mc.M_IRIT, mc.D_SS;
""".strip()


def _filename_component(value, fallback="NA", max_length=45):
    """Convert a grouping value to a filesystem-safe filename component."""
    if pd.isna(value) or str(value).strip() == "":
        text = fallback
    else:
        text = str(value).strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return (text or fallback)[:max_length]


def _scatterplot_filename(plot_number, row, columns):
    """Build a readable, unique PNG name from the aggregate row dimensions."""
    parts = [
        f"{plot_number:03d}",
        _filename_component(row[columns["SETTINGS_STUDY_TYPE"]]),
        _filename_component(row[columns["SETTINGS_D_SUBJECT"]]),
        _filename_component(row[columns["SETTINGS_D_MAPGROWTH_TEST_NAME"]]),
        "grade-" + _filename_component(row[columns["GRADE"]]),
        "agency-" + _filename_component(row[columns["AGENCY_CODE"]]),
    ]
    return "__".join(parts) + ".png"


def _create_scatterplot(detail_dataframe, aggregate_row, columns, output_file):
    """Save one M_IRIT versus D_SS scatterplot for a low-correlation group."""
    m_irit_column = _find_column(detail_dataframe, "M_IRIT")
    d_ss_column = _find_column(detail_dataframe, "D_SS")

    plot_data = pd.DataFrame(
        {
            "M_IRIT": pd.to_numeric(detail_dataframe[m_irit_column], errors="coerce"),
            "D_SS": pd.to_numeric(detail_dataframe[d_ss_column], errors="coerce"),
        }
    ).dropna()

    if plot_data.empty:
        print(f"  Skipping empty scatterplot: {output_file.name}")
        return False

    correlation = float(aggregate_row[columns["CORRELATION"]])
    title_parts = [
        str(aggregate_row[columns["SETTINGS_STUDY_TYPE"]]),
        str(aggregate_row[columns["SETTINGS_D_SUBJECT"]]),
        str(aggregate_row[columns["SETTINGS_D_MAPGROWTH_TEST_NAME"]]),
        f"Grade {aggregate_row[columns['GRADE']]}",
        f"Agency {aggregate_row[columns['AGENCY_CODE']]}",
    ]

    figure, axis = plt.subplots(figsize=(8, 6))
    axis.scatter(
        plot_data["M_IRIT"],
        plot_data["D_SS"],
        alpha=0.65,
        edgecolors="none",
    )
    axis.set_title(" | ".join(title_parts), fontsize=10, wrap=True)
    axis.set_xlabel("M_IRIT")
    axis.set_ylabel("D_SS")
    axis.grid(True, alpha=0.25)
    axis.text(
        0.02,
        0.98,
        f"Correlation = {correlation:.4f}\nN = {len(plot_data):,}",
        transform=axis.transAxes,
        verticalalignment="top",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
    )
    figure.tight_layout()
    figure.savefig(output_file, dpi=150, bbox_inches="tight")
    plt.close(figure)
    return True


def _create_low_correlation_scatterplots(dataframe, output_path):
    """Create one scatterplot for each low-correlation aggregate record."""
    required_columns = [
        "SETTINGS_STUDY_TYPE",
        "SETTINGS_D_SUBJECT",
        "SETTINGS_D_MAPGROWTH_TEST_NAME",
        "GRADE",
        "AGENCY_CODE",
        "CORRELATION",
    ]
    columns = {
        required_name: _find_column(dataframe, required_name)
        for required_name in required_columns
    }

    correlations = pd.to_numeric(dataframe[columns["CORRELATION"]], errors="coerce")
    low_correlation_rows = dataframe.loc[
        correlations.notna() & (correlations < LOW_CORRELATION_THRESHOLD)
    ]

    plot_directory = output_path.parent / LOW_CORRELATION_FOLDER_NAME
    plot_directory.mkdir(parents=True, exist_ok=True)

    # Remove plots from the preceding run so the folder reflects this workbook.
    for old_plot in plot_directory.glob("*.png"):
        old_plot.unlink()

    print(
        f"Low-correlation Study Grade Agency rows: "
        f"{len(low_correlation_rows):,}"
    )

    plots_created = 0
    for plot_number, (_, row) in enumerate(low_correlation_rows.iterrows(), start=1):
        detail_query = _build_scatter_detail_query(row, columns)
        query_result = query_snowflake_sqlalchemy(
            detail_query,
            SNOWFLAKEUSER,
            ROLE,
            WAREHOUSE,
            DATABASE=DATABASE,
            SCHEMA=SCHEMA,
        )
        detail_dataframe = _coerce_dataframe(
            query_result,
            f"{LOW_CORRELATION_SHEET} scatterplot {plot_number}",
        )
        output_file = plot_directory / _scatterplot_filename(
            plot_number,
            row,
            columns,
        )
        if _create_scatterplot(detail_dataframe, row, columns, output_file):
            plots_created += 1
            print(f"  Created scatterplot: {output_file.name}")

    print(f"Scatterplots created: {plots_created:,} in {plot_directory}")
    return plots_created


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

    results_by_sheet = dict(results)
    if LOW_CORRELATION_SHEET not in results_by_sheet:
        raise KeyError(
            f"Required worksheet result '{LOW_CORRELATION_SHEET}' was not produced."
        )
    _create_low_correlation_scatterplots(
        results_by_sheet[LOW_CORRELATION_SHEET],
        output_path,
    )


if __name__ == "__main__":
    main()
