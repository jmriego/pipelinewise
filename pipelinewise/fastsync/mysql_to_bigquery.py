#!/usr/bin/env python3
import logging
import os
import sys
import time
from functools import partial
from argparse import Namespace
import multiprocessing
from typing import Union

from datetime import datetime
from .commons import utils
from .commons.tap_mysql import FastSyncTapMySql
from .commons.target_bigquery import FastSyncTargetBigquery

from .. import utils as pipelinewise_utils
pipelinewise_utils.QUOTE_CHARACTER = '`'

MAX_NUM="99999999999999999999999999999.999999999"

LOGGER = logging.getLogger(__name__)

REQUIRED_CONFIG_KEYS = {
    'tap': [
        'host',
        'port',
        'user',
        'password'
    ],
    'target': [
        'project_id',
    ]
}

LOCK = multiprocessing.Lock()


def tap_type_to_target_type(mysql_type, mysql_column_type):
    """Data type mapping from MySQL to Bigquery"""
    return {
        'char':'STRING',
        'varchar':'STRING',
        'binary':'STRING',
        'varbinary':'STRING',
        'blob':'STRING',
        'tinyblob':'STRING',
        'mediumblob':'STRING',
        'longblob':'STRING',
        'geometry':'STRING',
        'text':'STRING',
        'tinytext':'STRING',
        'mediumtext':'STRING',
        'longtext':'STRING',
        'enum':'STRING',
        'int':'INT64',
        'tinyint':'BOOL' if mysql_column_type == 'tinyint(1)' else 'INT64',
        'smallint':'INT64',
        'mediumint':'INT64',
        'bigint':'INT64',
        'bit':'BOOL',
        'decimal':'NUMERIC',
        'double':'NUMERIC',
        'float':'NUMERIC',
        'bool':'BOOL',
        'boolean':'BOOL',
        'date':'TIMESTAMP',
        'datetime':'TIMESTAMP',
        'timestamp':'TIMESTAMP',
        'time':'TIME'
    }.get(mysql_type, 'STRING')


def sync_table(table: str, args: Namespace) -> Union[bool, str]:
    """Sync one table"""
    mysql = FastSyncTapMySql(args.tap, tap_type_to_target_type)
    bigquery = FastSyncTargetBigquery(args.target, args.transform)

    try:
        filename = 'pipelinewise_fastsync_{}_{}.csv'.format(table, time.strftime('%Y%m%d-%H%M%S'))
        filepath = os.path.join(args.temp_dir, filename)
        target_schema = utils.get_target_schema(args.target, table)

        # Open connection and get binlog file position
        mysql.open_connections()

        # Get bookmark - Binlog position or Incremental Key value
        bookmark = utils.get_bookmark_for_table(table, args.properties, mysql)

        # Exporting table data, get table definitions and close connection to avoid timeouts
        mysql.copy_table(table, filepath, max_num=MAX_NUM, date_type='datetime', compressed=False)
        size_bytes = os.path.getsize(filepath)
        bigquery_types = mysql.map_column_types_to_target(table)
        bigquery_columns = bigquery_types.get('columns', [])
        mysql.close_connections()

        # Creating temp table in Bigquery
        bigquery.create_schema(target_schema)
        bigquery.create_table(target_schema, table, bigquery_columns, is_temporary=True)

        # Load into Bigquery table
        bigquery.copy_to_table(filepath, target_schema, table, size_bytes, is_temporary=True, allow_quoted_newlines=False)
        os.remove(filepath)

        # Obfuscate columns
        bigquery.obfuscate_columns(target_schema, table)

        # Create target table and swap with the temp table in Bigquery
        bigquery.create_table(target_schema, table, bigquery_columns)
        bigquery.swap_tables(target_schema, table)

        # Save bookmark to singer state file
        # Lock to ensure that only one process writes the same state file at a time
        LOCK.acquire()
        try:
            utils.save_state_file(args.state, table, bookmark)
        finally:
            LOCK.release()

        # Table loaded, grant select on all tables in target schema
        grantees = utils.get_grantees(args.target, table)
        utils.grant_privilege(target_schema, grantees, bigquery.grant_usage_on_schema)
        utils.grant_privilege(target_schema, grantees, bigquery.grant_select_on_schema)

        return True

    except Exception as exc:
        LOGGER.exception(exc)
        return '{}: {}'.format(table, exc)


def main_impl():
    """Main sync logic"""
    args = utils.parse_args(REQUIRED_CONFIG_KEYS)
    cpu_cores = utils.get_cpu_cores()
    start_time = datetime.now()
    table_sync_excs = []

    # Log start info
    LOGGER.info("""
        -------------------------------------------------------
        STARTING SYNC
        -------------------------------------------------------
            Tables selected to sync        : %s
            Total tables selected to sync  : %s
            CPU cores                      : %s
        -------------------------------------------------------
        """, args.tables, len(args.tables), cpu_cores)

    # Start loading tables in parallel in spawning processes by
    # utilising all available CPU cores
    with multiprocessing.Pool(cpu_cores) as proc:
        table_sync_excs = list(
            filter(lambda x: not isinstance(x, bool), proc.map(partial(sync_table, args=args), args.tables)))

    # Log summary
    end_time = datetime.now()
    LOGGER.info("""
        -------------------------------------------------------
        SYNC FINISHED - SUMMARY
        -------------------------------------------------------
            Total tables selected to sync  : %s
            Tables loaded successfully     : %s
            Exceptions during table sync   : %s

            CPU cores                      : %s
            Runtime                        : %s
        -------------------------------------------------------
        """, len(args.tables), len(args.tables) - len(table_sync_excs), str(table_sync_excs),
                cpu_cores, end_time - start_time)

    if len(table_sync_excs) > 0:
        sys.exit(1)


def main():
    """Main entry point"""
    try:
        main_impl()
    except Exception as exc:
        LOGGER.critical(exc)
        raise exc
