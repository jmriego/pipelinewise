import os
import re
import pytest
import cli.utils

VIRTUALENVS_DIR="./virtualenvs-dummy"


class TestUtils(object):
    """
    Unit Tests for PipelineWise CLI utility functions
    """
    def test_json_detectors(self):
        """Testing JSON detector functions"""
        assert cli.utils.is_json("{Invalid JSON}") == False

        assert cli.utils.is_json("[]") == True
        assert cli.utils.is_json("{}") == True
        assert cli.utils.is_json('{"prop": 123}') == True
        assert cli.utils.is_json('{"prop-str":"dummy-string","prop-int":123,"prop-bool":true}') == True

        assert cli.utils.is_json_file("./dummy-json") == False
        assert cli.utils.is_json_file("{}/resources/example.json".format(os.path.dirname(__file__))) == True
        assert cli.utils.is_json_file("{}/resources/invalid.json".format(os.path.dirname(__file__))) == False
        assert cli.utils.is_json_file("{}/resources".format(os.path.dirname(__file__))) == False


    def test_json_loader(self):
        """Testing JSON loader functions"""
        # Loading JSON file that not exist should return None
        assert cli.utils.load_json("/invalid/location/to/json") is None

        # Loading JSON file with invalid JSON syntax should raise exception
        with pytest.raises(Exception):
            cli.utils.load_json("{}/resources/invalid.json".format(os.path.dirname(__file__)))

        # Loading JSON should return python dict
        assert \
            cli.utils.load_json("{}/resources/example.json".format(os.path.dirname(__file__))) == \
            {
                "glossary": {
                    "title": "example glossary",
                    "GlossDiv": {
                        "title": "S",
                        "GlossList": {
                            "GlossEntry": {
                                "ID": "SGML",
                                "SortAs": "SGML",
                                "GlossTerm": "Standard Generalized Markup Language",
                                "Acronym": "SGML",
                                "Abbrev": "ISO 8879:1986",
                                "GlossDef": {
                                    "para": "A meta-markup language, used to create markup languages such as DocBook.",
                                    "GlossSeeAlso": ["GML", "XML"]
                                },
                                "GlossSee": "markup"
                            }
                        }
                    }
                }
            }


    def test_json_saver(self):
        """Testing JSON save functions"""
        obj = {"foo": "bar"}
        # Saving to invalid path should raise exception
        with pytest.raises(Exception):
            cli.utils.save_json(obj, "/invalid/path")

        # Saving and reloading should match
        cli.utils.save_json(obj, "test-json.json")
        assert cli.utils.load_json("test-json.json") == obj

        # Delete output file, it's not required
        os.remove("test-json.json")


    def test_yaml_detectors(self):
        """Testing YAML detector functions"""
        assert cli.utils.is_yaml("""
            foo:
            -bar""") == False

        assert cli.utils.is_yaml("id: 123") == True
        assert cli.utils.is_yaml("""
            id: 123
            details:
                - prop1: 123
                - prop2: 456
            """) == True

        assert cli.utils.is_yaml_file("./dummy-yaml") == False
        assert cli.utils.is_yaml_file("{}/resources/example.yml".format(os.path.dirname(__file__))) == True 
        assert cli.utils.is_yaml_file("{}/resources/invalid.yml".format(os.path.dirname(__file__))) == False
        assert cli.utils.is_yaml_file("{}/resources".format(os.path.dirname(__file__))) == False


    def test_yaml_loader(self):
        """Testing YAML loader functions"""
        # Loading YAML file that not exist should return None
        assert cli.utils.load_yaml("/invalid/location/to/yaml") is None

        # Loading YAML file with invalid YAML syntax should raise exception
        with pytest.raises(Exception):
            cli.utils.load_yaml("{}/resources/invalid.yml".format(os.path.dirname(__file__)))

        # Loading JSON file with valid JSON syntax but invalid vault secret file should raise exception
        with pytest.raises(Exception):
            cli.utils.load_json("{}/resources/example.json".format(os.path.dirname(__file__)), "invalid-secret-file-path")

        # Loading valid YAML file with no vault encryption
        assert \
            cli.utils.load_yaml("{}/resources/example.yml".format(os.path.dirname(__file__))) == \
            ['Apple', 'Orange', 'Strawberry', 'Mango']

        # Loading valid YAML file with vault encrypted properties
        assert \
            cli.utils.load_yaml(
                "{}/resources/example-with-vault.yml".format(os.path.dirname(__file__)),
                "{}/resources/vault-secret.txt".format(os.path.dirname(__file__))) == \
            ['Apple', 'Orange', 'Strawberry', 'Mango', 'Vault Encrypted Secret Fruit']


    def test_sample_file_path(self):
        """Sample files must be a tap, target YAML or README file"""
        for sample in cli.utils.get_sample_file_paths():
            assert os.path.isfile(sample) == True
            assert \
                re.match(".*(tap|target)_.*.yml.sample$", sample) or re.match(".*README.md$", sample)


    def test_extract_log_attributes(self):
        """Log files must match to certain pattern with embedded attributes in the file name"""
        assert \
            cli.utils.extract_log_attributes("snowflake-fx-20190508_000038.singer.log.success") == \
            {
                'filename': 'snowflake-fx-20190508_000038.singer.log.success',
                'target_id': 'snowflake',
                'tap_id': 'fx',
                'timestamp': '2019-05-08T00:00:38',
                'sync_engine': 'singer',
                'status': 'success'
            }

        assert \
            cli.utils.extract_log_attributes("snowflake-fx-20190508_231238.fastsync.log.running") == \
            {
                'filename': 'snowflake-fx-20190508_231238.fastsync.log.running',
                'target_id': 'snowflake',
                'tap_id': 'fx',
                'timestamp': '2019-05-08T23:12:38',
                'sync_engine': 'fastsync',
                'status': 'running'
            }

        assert \
            cli.utils.extract_log_attributes("dummy-log-file.log") == \
            {
                'filename': 'dummy-log-file.log',
                'target_id': 'unknown',
                'tap_id': 'unknown',
                'timestamp': '1970-01-01T00:00:00',
                'sync_engine': 'unknown',
                'status': 'unknown'
            }
        

    def test_fastsync_bin(self):
        """Fastsync binary paths must point to certain virtual environments"""
        # Giving tap and target types should be enough to generate full path to fastsync binaries
        assert \
            cli.utils.get_fastsync_bin(VIRTUALENVS_DIR, 'mysql', 'snowflake') == \
            "{}/mysql-to-snowflake/bin/mysql-to-snowflake".format(VIRTUALENVS_DIR)


    def test_vault(self):
        """Test vault encrypt and decrypt functionalities"""
        # Encrypting with not existing file with secret should exit
        with pytest.raises(SystemExit) as pytest_wrapped_e:
            cli.utils.vault_encrypt("plain_test", "not-existing-secret-file")
        assert pytest_wrapped_e.type == SystemExit
        assert pytest_wrapped_e.value.code == 1

        # Encrypted string should start with $ANSIBLE_VAULT; identifier
        encrypted_str = str(cli.utils.vault_encrypt(
                "plain_text",
                "{}/resources/vault-secret.txt".format(os.path.dirname(__file__))))
        assert encrypted_str.startswith("b'$ANSIBLE_VAULT;") == True

        # Formatted encrypted string should start with special token and should keep the original vault encrypted value
        formatted_encrypted_str = cli.utils.vault_format_ciphertext_yaml(encrypted_str)
        assert formatted_encrypted_str.startswith("!vault |") and "b'$ANSIBLE_VAULT;" in formatted_encrypted_str

        # Optional name argument should add the name to the output string as a key
        formatted_encrypted_str = cli.utils.vault_format_ciphertext_yaml(encrypted_str, name="encrypted_plain_text")
        assert formatted_encrypted_str.startswith("encrypted_plain_text: !vault |") and "b'$ANSIBLE_VAULT;" in formatted_encrypted_str


    def test_schema_loader(self):
        """Test JSON Schema loader functions"""
        # Loading JSON schema file that not exist should exit
        with pytest.raises(SystemExit) as pytest_wrapped_e:
            cli.utils.load_schema("/invalid/location/to/schema") is None
        assert pytest_wrapped_e.type == SystemExit
        assert pytest_wrapped_e.value.code == 1

        # Loading existing JSON schema should be loaded correctly
        tap_schema = cli.utils.load_json("{}/../cli/schemas/tap.json".format(os.path.dirname(__file__)))
        assert cli.utils.load_schema("tap") == tap_schema


    def test_json_validate(self):
        """Test JSON schema validator functions"""
        schema = cli.utils.load_schema("tap")

        # Valid instance should return None
        valid_tap = cli.utils.load_yaml("{}/resources/tap-valid-mysql.yml".format(os.path.dirname(__file__)))
        assert cli.utils.validate(valid_tap, schema) is None

        # Invalid instance should exit
        invalid_tap = cli.utils.load_yaml("{}/resources/tap-invalid.yml".format(os.path.dirname(__file__)))
        with pytest.raises(SystemExit) as pytest_wrapped_e:
            cli.utils.validate(invalid_tap, schema)
        assert pytest_wrapped_e.type == SystemExit
        assert pytest_wrapped_e.value.code == 1


    def test_delete_keys(self):
        """Test dictionary functions"""
        # Delete single key with empty value
        assert cli.utils.delete_empty_keys(
            {"foo": "bar", "foo2": None}) == {"foo": "bar"}

        # Delete multiple keys with empty value
        assert cli.utils.delete_empty_keys(
            {"foo": "bar", "foo2": None, "foo3": None, "foo4": "bar4"}) == {"foo": "bar", "foo4": "bar4"}

        # Delete single key by name
        assert cli.utils.delete_keys_from_dict(
            {"foo": "bar", "foo2": "bar2"}, ["foo2"]) == {"foo": "bar"}

        # Delete single key by name
        assert cli.utils.delete_keys_from_dict(
            {"foo": "bar", "foo2": "bar2", "foo3": None, "foo4": "bar4"},["foo2", "foo4"]) == {"foo": "bar", "foo3": None}

        # Delete multiple keys from list of nested dictionaries
        assert cli.utils.delete_keys_from_dict(
            [{"foo": "bar", "foo2": "bar2"},
             {"foo3": {"nested_foo": "nested_bar", "nested_foo2": "nested_bar2"}}], ["foo2", "nested_foo"]) == \
             [{"foo": "bar"},
              {"foo3": {"nested_foo2": "nested_bar2"}}]


    def test_silentremove(self):
        """Test removing functions"""
        # Deleting non existing file should not raise exception
        assert cli.utils.silentremove("this-file-not-exists.json") is None


    def test_tap_properties(self):
        """Test tap property getter functions"""
        tap = cli.utils.load_yaml("{}/resources/tap-valid-mysql.yml".format(os.path.dirname(__file__)))

        # Every tap should have catalog argument --properties or --catalog
        tap_catalog_argument = cli.utils.get_tap_property(tap, "tap_catalog_argument")
        assert tap_catalog_argument == "--catalog" or tap_catalog_argument == "--properties"

        # Every tap should have extra_config_keys defined in dict
        assert isinstance(cli.utils.get_tap_extra_config_keys(tap), dict) == True

        # MySQL stream_id should be formatted as {{schema_name}}-{{table_name}}
        assert cli.utils.get_tap_stream_id(tap, "dummy_db", "dummy_schema", "dummy_table") == "dummy_schema-dummy_table"

        # MySQL stream_name should be formatted as {{schema_name}}-{{table_name}}
        assert cli.utils.get_tap_stream_name(tap, "dummy_db", "dummy_schema", "dummy_table") == "dummy_schema-dummy_table"

        # MySQL stream_name should be formatted as {{schema_name}}-{{table_name}}
        assert cli.utils.get_tap_default_replication_method(tap) == "LOG_BASED"

        # Get property value by tap type
        assert cli.utils.get_tap_property_by_tap_type("tap-mysql", "default_replication_method") == "LOG_BASED"


    def test_run_command(self):
        """Test run command functions

            Run command runs everything enclosed by /bin/bash -o pipefail -c '{}'
            This means arguments should pass as plain string after the command

            Return value is an array of: [return_code, stdout, stderr]
        """

        # Printing something to stdout should return 0
        [rc, stdout, stderr] =  cli.utils.run_command("echo this is a test line")
        assert [rc, stdout, stderr] == [0, "this is a test line\n", ""]

        # Running an invalid command should return 127 and some error message to stdout
        [rc, stdout, stderr] = cli.utils.run_command("invalid-command this is an invalid command")
        assert [rc, stdout] == [127, ""]
        assert stderr != ""

        # If loggin enabled then a success command should create log file with success status
        [rc, stdout, stderr] = cli.utils.run_command("echo this is a test line", log_file="./test.log")
        assert [rc, stdout, stderr] == [0, "this is a test line\n", None]
        os.path.isfile("test.log.success")
        os.remove("test.log.success")

        # If loggin enabled then a failed command should create log file with failed status
        # NOTE: When logging is enabled and the command fails then it raises an exception
        #       This behaviour is not in sync with no logging option
        # TODO: Sync failed command execution behaviour with logging and no-logging option
        #       Both should return [rc, stdout, stderr] list or both should raise exception
        with pytest.raises(Exception):
            [rc, stdout, stderr] = cli.utils.run_command("invalid-command this is an invalid command", log_file="./test.log")
        os.path.isfile("test.log.failed")
        os.remove("test.log.failed")
