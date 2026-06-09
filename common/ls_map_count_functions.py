# -*- coding: utf-8 -*-
"""
Created on Fri Jun 27 11:27:20 2025

@author: Chris.Wells

LS_MAP_Count_Functions.py

"""
#==============================================================================================
# CONNECTION: PUT THIS IN ANOTHER FILE
# MUST PROVIDE ROLE AND WAREHOUSE.  DB AND SCHEMA OPTIONAL
# EXAMPLE USAGE: 
    # SNOWFLAKEUSER = 'christopher.wells@hmhco.com'

    # ROLE = 'RESEARCH_PRD_MAPGROWTH_PSYCHOMETRIC_SOLUTIONS_FR'
    # WAREHOUSE = 'RESEARCH_PRD_MAPGROWTH_PSYCHOMETRIC_SOLUTIONS_WH'
    # DATABASE = 'RESEARCH_PRD_GRD_DB'
    # SCHEMA = 'LINKING_STUDIES'
    # CONN = establish_snowflake_connector(ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
#==============================================================================================

#dependencies
import snowflake.connector
import pandas as pd
import os
# import sqlalchemy 
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import text
from datetime import datetime
from pathlib import Path


def establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = '', SCHEMA = ''):
# Replace the placeholders with your Snowflake account details
    conn = snowflake.connector.connect(
        user = SNOWFLAKEUSER,
        account = "EJA57698",        
        authenticator = "externalbrowser",  
        role = ROLE,
        warehouse = WAREHOUSE,
        database = DATABASE,
        schema = SCHEMA
    )
    return conn



def establish_sqlalchemy_engine(
    SNOWFLAKEUSER: str,
    ROLE: str,
    WAREHOUSE: str,
    DATABASE: str = "",
    SCHEMA: str = "",
    ACCOUNT: str = "EJA57698",  # add region if needed, e.g., "EJA57698.us-west-2"
) -> Engine:
    """
    Create a SQLAlchemy Engine for Snowflake using external browser SSO,
    mirroring your connector settings.
    """
    # Build /DB[/SCHEMA] path; both are optional
    if DATABASE and SCHEMA:
        path = f"/{DATABASE}/{SCHEMA}"
    elif DATABASE:
        path = f"/{DATABASE}"
    else:
        path = ""

    # Compose SQLAlchemy Snowflake URL
    url = (
        f"snowflake://{SNOWFLAKEUSER}@{ACCOUNT}{path}"
        f"?authenticator=externalbrowser"
        f"&role={ROLE}"
        f"&warehouse={WAREHOUSE}"
    )

    engine = create_engine(
        url,
        pool_pre_ping=True,  # helps with stale pooled connections
        connect_args={
            "client_session_keep_alive": True,
            "session_parameters": {
                "QUERY_TAG": "linking_studies_pipeline",
                # "TIMEZONE": "UTC",  # uncomment if you want a fixed session tz
            },
        },
    )
    return engine



def query_snowflake_sqlalchemy(
    sql_query: str,
    SNOWFLAKEUSER: str,
    ROLE: str,
    WAREHOUSE: str,
    DATABASE: str = "",
    SCHEMA: str = "",
    ACCOUNT: str = "EJA57698",
) -> pd.DataFrame:
    """
    Open engine, run query, return DataFrame, close engine—just like your current helper.
    """
    engine = establish_sqlalchemy_engine(
        SNOWFLAKEUSER=SNOWFLAKEUSER,
        ROLE=ROLE,
        WAREHOUSE=WAREHOUSE,
        DATABASE=DATABASE,
        SCHEMA=SCHEMA,
        ACCOUNT=ACCOUNT,
    )

    # For plain SQL strings:
    with engine.connect() as conn:
        df = pd.read_sql(sql_query, conn)

        # If you prefer parameterized queries:
        # df = pd.read_sql(text("SELECT * FROM MY_TABLE WHERE event_date>=:d"), conn, params={"d": "2025-11-01"})

    # Dispose engine to close pool and underlying connections
    engine.dispose()
    return df




# def run_map_counts_query( sqlscript, variables, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = '', SCHEMA = ''):
    
def add_variables_to_sql_template(sqlscript, variables):
    """ run an sql query located in working directory 
        to be run on Snowflake for Map Growth Linking study
        
    Parameters
    ----------
    countsQuery : TYPE
        DESCRIPTION.
    variables : TYPE
        DESCRIPTION.
    SNOWFLAKEUSER : TYPE
        DESCRIPTION.
    ROLE : TYPE
        DESCRIPTION.
    WAREHOUSE : TYPE
        DESCRIPTION.
    DATABASE : TYPE, optional
        DESCRIPTION. The default is ''.
    SCHEMA : TYPE, optional
        DESCRIPTION. The default is ''.

    Returns
    -------
    df : TYPE
        DESCRIPTION.
    sql_template : TYPE
        DESCRIPTION.

    """    

    # LOAD EOG QUERY BY GRADE USING KNOWN TESTNAMES
    with open(sqlscript, "r") as f:
        sql_template = f.read()
        
    #replace keyholders
    for key, value in variables.items():
        sql_template = sql_template.replace(f"${key}", value)        
  
    # #open conn and run query
    # CONN = establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
    # df = pd.read_sql(sql_template, CONN)   
    # CONN.close()
    
    # return df, sql_template
    # return df, sql_template
    return sql_template

def query_snowflake(sql_query, SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = '', SCHEMA = ''):
    #open conn and run query
    CONN = establish_snowflake_connector(SNOWFLAKEUSER, ROLE, WAREHOUSE, DATABASE = DATABASE, SCHEMA = SCHEMA)
    df = pd.read_sql(sql_query, CONN)   
    CONN.close()
    return df


def output_to_excel_tab(outputDict, outpath):
    """output a pandas dataframe to specified excel tab.
       uses excelwriter so multiple tabs can be added.

    Parameters
    ----------
    outputDict : df
        dictionary of outptut. keys = tabnames, values = dataframe to output
    outpath : string
        excel path to output including path, filename and extension (.xlsx)
        eg. S:\MAPGrowth\Linking\Data Files\2024\GA202402_mapcounts.xlsx    
    tab : string
        excel tab name

    Returns
    -------
    None.

    """
    
    writer = pd.ExcelWriter(outpath, engine='xlsxwriter')
    for sheet_name, df in outputDict.items():
        df.to_excel (writer, sheet_name = sheet_name, index = False)
        
    writer.close()
    print('output ' + sheet_name +' to : ' + outpath)
    



def add_timestamp_to_filename(
    base_filename: str,
    outdir: str,
    timestamp_fmt: str = "%Y%m%d_%H%M%S"
) -> str:
    """
    Append a timestamp to a filename before the extension.

    Example:
        output_partner_counts.xlsx
        -> output_partner_counts_20260609_141233.xlsx
    """
    name, ext = os.path.splitext(base_filename)
    timestamp = datetime.now().strftime(timestamp_fmt)
    return os.path.join(outdir, f"{name}_{timestamp}{ext}")
    


def add_timestamp_to_path(
    outpath: Path,
    timestamp_fmt: str = "%Y%m%d_%H%M%S"
) -> Path:
    """
    Insert a timestamp before the file extension of a Path.

    Example:
      VA2025_partner_counts.xlsx
      -> VA2025_partner_counts_20260609_142015.xlsx
    """
    timestamp = datetime.now().strftime(timestamp_fmt)
    return outpath.with_name(
        f"{outpath.stem}_{timestamp}{outpath.suffix}"
    )
    
    
    

    
                