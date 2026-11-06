
# -*- coding: utf-8 -*-
"""
Create the linking-study STUDYSAMPLE_QA table in Snowflake.

This runner executes merge_linking_study_to_studysample_qa_v2.sql, which uses
seven ordered match phases to link partner records to MAP Growth test events.

The script follows the same project conventions as the MAP Growth table runner:
- project settings are read from pycode.settings
- SQL variables are inserted with add_variables_to_sql_template
- execution uses query_snowflake_sqlalchemy
"""

from pathlib import Path
import sys


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


def _setting_or_default(setting_name, default_value):
    """Return a nonblank optional settings value, otherwise use the default."""
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


state_code = str(STATE_ABR).strip().upper()
data_year = str(DATA_YEAR).strip()

# Optional settings values are honored when present. Defaults match the naming
# convention used by the existing Snowflake replacement query.
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
    "MERGED_TABLE_NAME": _fully_qualified_table_name(merged_table),
    "PARTNER_TABLE_NAME": _fully_qualified_table_name(partner_table),
    "SETTINGS_TABLE_NAME": _fully_qualified_table_name(settings_table),
    "MAP_GROWTH_TABLE_NAME": _fully_qualified_table_name(map_growth_table),
}


print(f"SQL template: {SQL_SCRIPT}")
print("Target tables:")
for variable_name, table_name in variables.items():
    print(f"  {variable_name}: {table_name}")

query_create_studysample_qa = add_variables_to_sql_template(
    str(SQL_SCRIPT),
    variables,
)

query_snowflake_sqlalchemy(
    query_create_studysample_qa,
    SNOWFLAKEUSER,
    ROLE,
    WAREHOUSE,
    DATABASE=DATABASE,
    SCHEMA=SCHEMA,
)
