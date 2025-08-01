import json

import pytest

from dbt.contracts.results import RunStatus
from dbt.tests.util import run_dbt, run_dbt_and_capture

models__table_base_model = """
{{
  config(
    materialized='incremental',
    incremental_strategy='append',
    on_schema_change=var("on_schema_change"),
    table_type=var("table_type"),
  )
}}

select
    1 as id,
    'test 1' as name
{%- if is_incremental() -%}
    ,current_date as updated_at
{%- endif -%}
"""


class TestOnSchemaChange:
    @pytest.fixture(scope="class")
    def models(self):
        models = {}
        for table_type in ["hive", "iceberg"]:
            for on_schema_change in ["sync_all_columns", "append_new_columns", "ignore", "fail"]:
                models[f"{table_type}_on_schema_change_{on_schema_change}.sql"] = (
                    models__table_base_model
                )
        return models

    def _column_names(self, project, relation_name):
        result = project.run_sql(f"show columns from {relation_name}", fetch="all")
        column_names = [row[0].strip() for row in result]
        return column_names

    @pytest.mark.parametrize("table_type", ["hive", "iceberg"])
    def test__sync_all_columns(self, project, table_type):
        relation_name = f"{table_type}_on_schema_change_sync_all_columns"
        vars = {"on_schema_change": "sync_all_columns", "table_type": table_type}
        args = ["run", "--select", relation_name, "--vars", json.dumps(vars)]

        model_run_initial = run_dbt(args)
        assert model_run_initial.results[0].status == RunStatus.Success

        model_run_incremental = run_dbt(args)
        assert model_run_incremental.results[0].status == RunStatus.Success

        new_column_names = self._column_names(project, relation_name)
        assert new_column_names == ["id", "name", "updated_at"]

    @pytest.mark.parametrize("table_type", ["hive", "iceberg"])
    def test__append_new_columns(self, project, table_type):
        relation_name = f"{table_type}_on_schema_change_append_new_columns"
        vars = {"on_schema_change": "append_new_columns", "table_type": table_type}
        args = ["run", "--select", relation_name, "--vars", json.dumps(vars)]

        model_run_initial = run_dbt(args)
        assert model_run_initial.results[0].status == RunStatus.Success

        model_run_incremental = run_dbt(args)
        assert model_run_incremental.results[0].status == RunStatus.Success

        new_column_names = self._column_names(project, relation_name)
        assert new_column_names == ["id", "name", "updated_at"]

    @pytest.mark.parametrize("table_type", ["hive", "iceberg"])
    def test__ignore(self, project, table_type):
        relation_name = f"{table_type}_on_schema_change_ignore"
        vars = {"on_schema_change": "ignore", "table_type": table_type}
        args = ["run", "--select", relation_name, "--vars", json.dumps(vars)]

        model_run_initial = run_dbt(args)
        assert model_run_initial.results[0].status == RunStatus.Success

        model_run_incremental = run_dbt(args)
        assert model_run_incremental.results[0].status == RunStatus.Success

        new_column_names = self._column_names(project, relation_name)
        assert new_column_names == ["id", "name"]

    @pytest.mark.parametrize("table_type", ["hive", "iceberg"])
    def test__fail(self, project, table_type):
        relation_name = f"{table_type}_on_schema_change_fail"
        vars = {"on_schema_change": "fail", "table_type": table_type}
        args = ["run", "--select", relation_name, "--vars", json.dumps(vars)]

        model_run_initial = run_dbt(args)
        assert model_run_initial.results[0].status == RunStatus.Success

        model_run_incremental, log = run_dbt_and_capture(args, expect_pass=False)
        assert model_run_incremental.results[0].status == RunStatus.Error
        assert "The source and target schemas on this incremental model are out of sync!" in log

        new_column_names = self._column_names(project, relation_name)
        assert new_column_names == ["id", "name"]


# Test fixtures for special character column names
models__table_special_chars_model = """
{{
  config(
    materialized='incremental',
    incremental_strategy='append',
    on_schema_change=var("on_schema_change"),
    table_type=var("table_type"),
  )
}}

select
    1 as id,
    'keyword' as "select"
{%- if is_incremental() -%}
    ,'new data' as "field-with-dash"
{%- endif -%}
"""


class TestOnSchemaChangeSpecialChars:
    """Test schema changes with special character column names for Athena

    Tests column quoting with SQL keywords and dashes in column names.
    """

    @pytest.fixture(scope="class")
    def models(self):
        models = {}
        for table_type in ["hive", "iceberg"]:
            for on_schema_change in ["sync_all_columns", "append_new_columns"]:
                models[f"{table_type}_special_chars_{on_schema_change}.sql"] = (
                    models__table_special_chars_model
                )
        return models

    def _column_names(self, project, relation_name):
        result = project.run_sql(f"show columns from {relation_name}", fetch="all")
        column_names = [row[0].strip() for row in result]
        return column_names

    @pytest.mark.parametrize("table_type", ["hive", "iceberg"])
    def test__append_new_columns_special_chars(self, project, table_type):
        """Test that columns with special characters are properly quoted when added"""
        relation_name = f"{table_type}_special_chars_append_new_columns"
        vars = {"on_schema_change": "append_new_columns", "table_type": table_type}
        args = ["run", "--select", relation_name, "--vars", json.dumps(vars)]

        # First run - creates initial table with quoted column names
        run_dbt(args)

        # Second run - should append new columns with special characters
        run_dbt(args)

        # Verify all columns including ones with special characters exist
        new_column_names = self._column_names(project, relation_name)
        expected_columns = [
            "id",
            "select",
            "field-with-dash",
        ]
        assert sorted(new_column_names) == sorted(expected_columns)

    def test__sync_all_columns_special_chars(self, project):
        """Test that columns with special characters are properly quoted when synced (add/remove)"""
        relation_name = "hive_special_chars_sync_all_columns"
        vars = {"on_schema_change": "sync_all_columns", "table_type": "hive"}
        args = ["run", "--select", relation_name, "--vars", json.dumps(vars)]

        # First run - creates initial table
        run_dbt(args)

        # Second run - should sync columns (replace all columns)
        run_dbt(args)

        # Verify columns were properly synced
        new_column_names = self._column_names(project, relation_name)
        expected_columns = [
            "id",
            "select",
            "field-with-dash",
        ]
        assert sorted(new_column_names) == sorted(expected_columns)
