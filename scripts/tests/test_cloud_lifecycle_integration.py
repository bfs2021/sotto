import importlib.util
from importlib.machinery import SourceFileLoader
import os
import subprocess
import sys
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
LOADER = SourceFileLoader(
    "check_cloud_lifecycle_integration", str(ROOT / "scripts/check-cloud-lifecycle-integration")
)
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = MODULE
LOADER.exec_module(MODULE)


class LifecycleManifest(unittest.TestCase):
    def test_manifest_has_unique_named_tests(self):
        test_cases = [(target, test_name) for _, target, test_name in MODULE.SCENARIOS]
        self.assertEqual(len(MODULE.SCENARIOS), 27)
        self.assertEqual(len(test_cases), len(set(test_cases)))
        self.assertTrue(all(label and target and test_name for label, target, test_name in MODULE.SCENARIOS))

    def test_discovery_must_include_every_required_case(self):
        discovered = {}
        for _, target, test_name in MODULE.SCENARIOS:
            discovered.setdefault(target, set()).add(test_name)
        MODULE.check_manifest(discovered)

        target = MODULE.SCENARIOS[0][1]
        missing = MODULE.SCENARIOS[0][2]
        discovered[target].remove(missing)
        with self.assertRaisesRegex(RuntimeError, "lifecycle test discovery failed"):
            MODULE.check_manifest(discovered)

    def test_every_run_must_execute_at_least_one_test(self):
        with self.assertRaisesRegex(RuntimeError, "selected zero tests"):
            MODULE.RUNNER.assert_tests_selected(
                "test result: ok. 0 passed; 0 failed; 0 ignored\n", "empty lifecycle case"
            )

    def test_runner_requires_database_opt_in_and_local_database(self):
        with self.assertRaisesRegex(ValueError, "SOTTO_RUN_DB_TESTS"):
            MODULE.validate_acceptance_database({"DATABASE_URL": "postgres://localhost/sotto_lifecycle_acceptance"})
        with self.assertRaisesRegex(ValueError, "local disposable"):
            MODULE.validate_acceptance_database(
                {
                    "SOTTO_RUN_DB_TESTS": "1",
                    "DATABASE_URL": "postgres://database.example/sotto_lifecycle_acceptance",
                }
            )
        with self.assertRaisesRegex(ValueError, "name ends"):
            MODULE.validate_acceptance_database(
                {
                    "SOTTO_RUN_DB_TESTS": "1",
                    "DATABASE_URL": "postgres://localhost/sotto",
                }
            )
        MODULE.validate_acceptance_database(
            {
                "SOTTO_RUN_DB_TESTS": "1",
                "DATABASE_URL": "postgres://localhost/sotto_cloud_lifecycle_acceptance",
            }
        )

    def test_postgres_cli_credentials_are_taken_from_url_without_leaking_into_args(self):
        connection = MODULE.postgres_connection(
            "postgres://sotto:p%40ss@127.0.0.1:5433/sotto_lifecycle_acceptance"
        )
        env = MODULE.postgres_cli_env({}, connection)
        self.assertEqual(env["PGHOST"], "127.0.0.1")
        self.assertEqual(env["PGPORT"], "5433")
        self.assertEqual(env["PGUSER"], "sotto")
        self.assertEqual(env["PGPASSWORD"], "p@ss")

    def test_disposable_database_is_dropped_after_test_failure(self):
        env = {
            "SOTTO_RUN_DB_TESTS": "1",
            "DATABASE_URL": "postgres://sotto:p%40ss@localhost:5432/sotto_lifecycle_acceptance",
        }
        calls = []

        def utility(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(MODULE.secrets, "token_hex", return_value="deadbeef"):
            with mock.patch.object(MODULE.subprocess, "run", side_effect=utility):
                with self.assertRaisesRegex(RuntimeError, "simulated test failure"):
                    with MODULE.disposable_acceptance_database(env) as test_env:
                        self.assertEqual(
                            test_env["DATABASE_URL"],
                            "postgres://sotto:p%40ss@localhost:5432/sotto_lifecycle_acceptance_deadbeef",
                        )
                        raise RuntimeError("simulated test failure")
        self.assertEqual([call[0][0] for call in calls], ["createdb", "dropdb"])
        self.assertNotIn("p@ss", " ".join(calls[0][0]))
        self.assertEqual(calls[0][1]["env"]["PGPASSWORD"], "p@ss")

    def test_database_cleanup_failure_is_reported(self):
        env = {
            "SOTTO_RUN_DB_TESTS": "1",
            "DATABASE_URL": "postgres://localhost/sotto_lifecycle_acceptance",
        }

        def utility(command, **kwargs):
            status = 0 if command[0] == "createdb" else 1
            return subprocess.CompletedProcess(command, status, "", "cleanup failed")

        with mock.patch.object(MODULE.secrets, "token_hex", return_value="deadbeef"):
            with mock.patch.object(MODULE.subprocess, "run", side_effect=utility):
                with self.assertRaisesRegex(RuntimeError, "dropdb failed"):
                    with MODULE.disposable_acceptance_database(env):
                        pass

    def test_cli_fails_closed_without_database_configuration(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(MODULE.main([]), 1)

    def test_non_positive_timeout_is_rejected(self):
        with self.assertRaises(SystemExit) as error:
            MODULE.main(["--timeout", "0"])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
