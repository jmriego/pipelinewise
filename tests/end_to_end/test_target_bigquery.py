import os
import uuid
from datetime import datetime
from random import randint

import bson
import pytest
from bson import Timestamp

from .helpers import tasks
from .helpers import assertions
from .helpers.env import E2EEnv

DIR = os.path.dirname(__file__)
TAP_MARIADB_ID = 'mariadb_to_bq'
TAP_POSTGRES_ID = 'postgres_to_bq'
TAP_MONGODB_ID = 'mongo_to_bq'
TARGET_ID = 'bigquery'


# pylint: disable=attribute-defined-outside-init
class TestTargetBigquery:
    """
    End to end tests for Target Bigquery
    """

    def setup_method(self):
        """Initialise test project by generating YAML files from
        templates for all the configured connectors"""
        self.project_dir = os.path.join(DIR, 'test-project')

        # Init query runner methods
        self.e2e = E2EEnv(self.project_dir)
        self.run_query_tap_mysql = self.e2e.run_query_tap_mysql
        self.run_query_tap_postgres = self.e2e.run_query_tap_postgres
        self.run_query_target_bigquery = self.e2e.run_query_target_bigquery
        self.mongodb_con = self.e2e.get_tap_mongodb_connection()

    def teardown_method(self):
        """Delete test directories and database objects"""

    @pytest.mark.dependency(name='import_config')
    def test_import_project(self):
        """Import the YAML project with taps and target and do discovery mode
        to write the JSON files for singer connectors """

        # Skip every target_postgres related test if required env vars not provided
        if not self.e2e.env['TARGET_BIGQUERY']['is_configured']:
            pytest.skip('Target Bigquery environment variables are not provided')

        # Setup and clean source and target databases
        self.e2e.setup_tap_mysql()
        self.e2e.setup_tap_postgres()
        if self.e2e.env['TAP_S3_CSV']['is_configured']:
            self.e2e.setup_tap_s3_csv()
        self.e2e.setup_tap_mongodb()
        self.e2e.setup_target_bigquery()

        # Import project
        print(f'JM pipelinewise import_config --dir {self.project_dir}')
        [return_code, stdout, stderr] = tasks.run_command(f'pipelinewise import_config --dir {self.project_dir}')
        assertions.assert_command_success(return_code, stdout, stderr)

    @pytest.mark.dependency(depends=['import_config'])
    def test_replicate_mariadb_to_bq(self):
        """Replicate data from MariaDB to Bigquery"""
        # Run tap first time - both fastsync and a singer should be triggered
        assertions.assert_run_tap_success(TAP_MARIADB_ID, TARGET_ID, ['fastsync', 'singer'])
        assertions.assert_row_counts_equal(self.run_query_tap_mysql, self.run_query_target_bigquery)
        assertions.assert_all_columns_exist(self.run_query_tap_mysql, self.e2e.run_query_target_bigquery)

        # 2. Make changes in MariaDB source database
        #  LOG_BASED
        self.run_query_tap_mysql('UPDATE weight_unit SET isactive = 0 WHERE weight_unit_id IN (2, 3, 4)')
        #  INCREMENTAL
        self.run_query_tap_mysql('INSERT INTO address(isactive, street_number, date_created, date_updated,'
                                 ' supplier_supplier_id, zip_code_zip_code_id)'
                                 'VALUES (1, 1234, NOW(), NOW(), 0, 1234)')
        self.run_query_tap_mysql('UPDATE address SET street_number = 9999, date_updated = NOW()'
                                 ' WHERE address_id = 1')
        #  FULL_TABLE
        self.run_query_tap_mysql('DELETE FROM no_pk_table WHERE id > 10')

        # 3. Run tap second time - both fastsync and a singer should be triggered, there are some FULL_TABLE
        assertions.assert_run_tap_success(TAP_POSTGRES_ID, TARGET_ID, ['fastsync', 'singer'])
        assertions.assert_row_counts_equal(self.run_query_tap_postgres, self.run_query_target_bigquery)
        assertions.assert_all_columns_exist(self.run_query_tap_mysql, self.e2e.run_query_target_bigquery)

    @pytest.mark.dependency(depends=['import_config'])
    def test_replicate_pg_to_bq(self):
        """Replicate data from Postgres to Bigquery"""
        # Run tap first time - both fastsync and a singer should be triggered
        assertions.assert_run_tap_success(TAP_POSTGRES_ID, TARGET_ID, ['fastsync', 'singer'])
        assertions.assert_row_counts_equal(self.run_query_tap_postgres, self.run_query_target_bigquery)
        assertions.assert_all_columns_exist(self.run_query_tap_postgres, self.e2e.run_query_target_bigquery)

        # 2. Make changes in MariaDB source database
        #  LOG_BASED - Missing due to some changes that's required in tap-postgres to test it automatically
        #  INCREMENTAL
        self.run_query_tap_postgres('INSERT INTO public.city (id, name, countrycode, district, population) '
                                    "VALUES (4080, 'Bath', 'GBR', 'England', 88859)")
        self.run_query_tap_postgres('UPDATE public.edgydata SET '
                                    "cjson = json '{\"data\": 1234}', "
                                    "cjsonb = jsonb '{\"data\": 2345}', "
                                    "cvarchar = 'Liewe Maatjies UPDATED' WHERE cid = 23")
        #  FULL_TABLE
        self.run_query_tap_postgres("DELETE FROM public.country WHERE code = 'UMI'")

        # 3. Run tap second time - both fastsync and a singer should be triggered, there are some FULL_TABLE
        assertions.assert_run_tap_success(TAP_POSTGRES_ID, TARGET_ID, ['fastsync', 'singer'])
        assertions.assert_row_counts_equal(self.run_query_tap_postgres, self.run_query_target_bigquery)
        assertions.assert_all_columns_exist(self.run_query_tap_postgres, self.e2e.run_query_target_bigquery)

    @pytest.mark.dependency(depends=['import_config'])
    def test_replicate_mongodb_to_bq(self):
        """Replicate mongodb to Bigquery"""

        def assert_columns_exist(table):
            """Helper inner function to test if every table and column exists in the target"""
            assertions.assert_cols_in_table(self.run_query_target_bigquery, 'ppw_e2e_tap_mongodb', table,
                                            ['_ID', 'DOCUMENT', '_SDC_EXTRACTED_AT',
                                             '_SDC_BATCHED_AT', '_SDC_DELETED_AT'])

        def assert_row_counts_equal(target_schema, table, count_in_source):
            assert count_in_source == \
                   self.run_query_target_bigquery(f'select count(_id) from {target_schema}.{table}')[0][0]

        # Run tap first time - fastsync and singer should be triggered
        assertions.assert_run_tap_success(TAP_MONGODB_ID, TARGET_ID, ['fastsync', 'singer'])
        assert_columns_exist('listings')
        assert_columns_exist('my_collection')

        listing_count = self.mongodb_con['listings'].count_documents({})
        my_coll_count = self.mongodb_con['my_collection'].count_documents({})

        assert_row_counts_equal('ppw_e2e_tap_mongodb', 'listings', listing_count)
        assert_row_counts_equal('ppw_e2e_tap_mongodb', 'my_collection', my_coll_count)

        result_insert = self.mongodb_con.my_collection.insert_many([
            {
                'age': randint(10, 30),
                'id': 1001,
                'uuid': uuid.uuid4(),
                'ts': Timestamp(12030, 500)
            },
            {
                'date': datetime.utcnow(),
                'id': 1002,
                'uuid': uuid.uuid4(),
                'regex': bson.Regex(r'^[A-Z]\\w\\d{2,6}.*$')
            },
            {
                'uuid': uuid.uuid4(),
                'id': 1003,
                'nested_json': {'a': 1, 'b': 3, 'c': {'key': bson.datetime.datetime(2020, 5, 3, 10, 0, 0)}}
            }
        ])
        my_coll_count += len(result_insert.inserted_ids)

        result_del = self.mongodb_con.my_collection.delete_one({'_id': result_insert.inserted_ids[0]})
        my_coll_count -= result_del.deleted_count

        result_update = self.mongodb_con.my_collection.update_many({}, {'$set': {'id': 0}})

        assertions.assert_run_tap_success(TAP_MONGODB_ID, TARGET_ID, ['fastsync', 'singer'])

        assert result_update.modified_count == self.run_query_target_bigquery(
            'select count(_id) from ppw_e2e_tap_mongodb.my_collection where document:id = 0')[0][0]

        assert_row_counts_equal('ppw_e2e_tap_mongodb', 'my_collection', my_coll_count)
