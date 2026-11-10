# -*- coding: utf-8 -*-
"""
Create the linking-study STUDYSAMPLE_QA table in Snowflake.

This runner executes merge_linking_study_to_studysample_qa_v2.sql.

On failure:
- prints a short Snowflake error to the console
- writes the complete traceback to snowflake_error.log
- writes the rendered SQL to failed_query.sql
- exits with a nonzero status
"""

from pathlib import Path
import sys
import traceback

from sqlalchemy.exc import SQLAlchemyError


# -----------------------------------------------------------------------------
# Set the project root to Linking_Studies_Data_Prep_Code.
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


from common.ls_map_count_functions import add_variables_to_sql_template
from common.ls_map_count_functions import query_snowflake_sqlalchemy
from pycode.settings import *


SQL_PATH = ROOT / "common" / "py_sql"
SQL_SCRIPT = SQL_PATH / "merge_linking_study_to_studysample_qa_v2.sql"

ERROR_LOG = ROOT / "snowflake_error.log"
FAILED_SQL_LOG = ROOT / "failed_query.sql"


def _setting_or_default(setting_name, default_value):
    """Return a nonblank optional setting or the supplied default."""
    value = globals().get(setting_name)

    if value is None or str(value).strip() == "":
        return default_value

    return str(value).strip()


def _fully_qualified_table_name(table_name):
    """Qualify an unqualified table with the configured database and schema."""
    table_name = str(table_name).strip()

    if table_name.count(".") == 2:
        return table_name

    if table_name.count(".") == 1:
        return f"{DATABASE}.{table_name}"

    return f"{DATABASE}.{SCHEMA}.{table_name}"


def _get_short_error_message(exc):
    """
    Return the underlying database message without SQLAlchemy's full SQL text.
    """
    original_error = getattr(exc, "orig", None)

    if original_error is not None:
        # Snowflake exceptions normally expose a concise message in `msg`.
        original_message = getattr(original_error, "msg", None)

        if original_message:
            return str(original_message)

        # If `msg` is unavailable, use only the first line.
        return str(original_error).splitlines()[0]

    # Avoid printing a potentially enormous SQLAlchemy exception.
    return str(exc).splitlines()[0]


def _write_failure_files(exc, rendered_sql):
    """Write detailed diagnostics to files without flooding the console."""
    try:
        with ERROR_LOG.open(
            "w",
            encoding="utf-8",
            errors="replace",
        ) as error_file:
            error_file.write("SNOWFLAKE SQL EXECUTION FAILURE\n")
            error_file.write("=" * 80)
            error_file.write("\n\n")

            error_file.write(
                f"Exception type: {type(exc).__name__}\n"
            )

            original_error = getattr(exc, "orig", None)

            if original_error is not None:
                error_file.write(
                    "Underlying exception type: "
                    f"{type(original_error).__name__}\n"
                )

                for attribute_name in (
                    "errno",
                    "sqlstate",
                    "sfqid",
                    "query_id",
                    "msg",
                ):
                    attribute_value = getattr(
                        original_error,
                        attribute_name,
                        None,
                    )

                    if attribute_value not in (None, ""):
                        error_file.write(
                            f"{attribute_name}: "
                            f"{attribute_value}\n"
                        )

            error_file.write("\nFull traceback:\n")
            error_file.write("-" * 80)
            error_file.write("\n")

            traceback.print_exception(
                type(exc),
                exc,
                exc.__traceback__,
                file=error_file,
            )

    except Exception as log_error:
        print(
            "Warning: could not write the error log: "
            f"{type(log_error).__name__}",
            file=sys.stderr,
            flush=True,
        )

    if rendered_sql:
        try:
            FAILED_SQL_LOG.write_text(
                str(rendered_sql),
                encoding="utf-8",
                errors="replace",
            )

        except Exception as sql_log_error:
            print(
                "Warning: could not write the failed SQL file: "
                f"{type(sql_log_error).__name__}",
                file=sys.stderr,
                flush=True,
            )


def _display_short_error(exc):
    """Display only concise diagnostic information in the console."""
    original_error = getattr(exc, "orig", None)

    print(
        "\nSnowflake SQL execution failed.",
        file=sys.stderr,
        flush=True,
    )

    print(
        f"Error type: {type(exc).__name__}",
        file=sys.stderr,
        flush=True,
    )

    if original_error is not None:
        print(
            "Snowflake error type: "
            f"{type(original_error).__name__}",
            file=sys.stderr,
            flush=True,
        )

        for attribute_name in (
            "errno",
            "sqlstate",
            "sfqid",
            "query_id",
        ):
            attribute_value = getattr(
                original_error,
                attribute_name,
                None,
            )

            if attribute_value not in (None, ""):
                print(
                    f"{attribute_name}: {attribute_value}",
                    file=sys.stderr,
                    flush=True,
                )

    print(
        f"Message: {_get_short_error_message(exc)}",
        file=sys.stderr,
        flush=True,
    )

    print(
        f"Full traceback written to: {ERROR_LOG}",
        file=sys.stderr,
        flush=True,
    )

    print(
        f"Failed SQL written to: {FAILED_SQL_LOG}",
        file=sys.stderr,
        flush=True,
    )


def main():
    """Render and execute the STUDYSAMPLE_QA SQL."""
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

    map_growth_table = _setting_or_default(
        "map_table_name",
        f"{state_code}{data_year}_MAP_DATA",
    )

    variables = {
        "MERGED_TABLE_NAME": _fully_qualified_table_name(
            merged_table
        ),
        "PARTNER_TABLE_NAME": _fully_qualified_table_name(
            partner_table
        ),
        "SETTINGS_TABLE_NAME": _fully_qualified_table_name(
            settings_table
        ),
        "MAP_GROWTH_TABLE_NAME": _fully_qualified_table_name(
            map_growth_table
        ),
    }

    print(
        f"SQL template: {SQL_SCRIPT}",
        flush=True,
    )

    print(
        "Target tables:",
        flush=True,
    )

    for variable_name, table_name in variables.items():
        print(
            f" {variable_name}: {table_name}",
            flush=True,
        )

    rendered_sql = None

    try:
        if not SQL_SCRIPT.exists():
            raise FileNotFoundError(
                f"SQL template was not found: {SQL_SCRIPT}"
            )

        print(
            "Rendering SQL template...",
            flush=True,
        )

        rendered_sql = add_variables_to_sql_template(
            str(SQL_SCRIPT),
            variables,
        )

        if rendered_sql is None:
            raise RuntimeError(
                "SQL template rendering returned None."
            )

        if not str(rendered_sql).strip():
            raise RuntimeError(
                "The rendered SQL is empty."
            )

        print(
            "Executing SQL in Snowflake...",
            flush=True,
        )

        result = query_snowflake_sqlalchemy(
            rendered_sql,
            SNOWFLAKEUSER,
            ROLE,
            WAREHOUSE,
            DATABASE=DATABASE,
            SCHEMA=SCHEMA,
        )

        print(
            "Snowflake SQL execution completed successfully.",
            flush=True,
        )

        return 0

    except SQLAlchemyError as exc:
        _write_failure_files(
            exc,
            rendered_sql,
        )

        _display_short_error(exc)

        return 1

    except Exception as exc:
        _write_failure_files(
            exc,
            rendered_sql,
        )

        _display_short_error(exc)

        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)