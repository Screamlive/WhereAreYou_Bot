import sqlite3
import sys
import tempfile
import unittest
import warnings
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from app.ops import backup_ops, broadcast_ops, cli, run_ops


class BroadcastOpsTests(unittest.TestCase):
    def test_build_broadcast_args_changelog(self):
        args = broadcast_ops.build_broadcast_args(
            audience="approved",
            text=None,
            file_path=None,
            changelog_latest="CHANGELOG.md",
            limit=10,
            delay=0.2,
            dry_run=True,
        )
        self.assertIn("--audience", args)
        self.assertIn("approved", args)
        self.assertIn("--changelog-latest", args)
        self.assertIn("CHANGELOG.md", args)
        self.assertIn("--dry-run", args)

    def test_build_broadcast_args_requires_source(self):
        with self.assertRaises(ValueError):
            broadcast_ops.build_broadcast_args(
                audience="approved",
                text=None,
                file_path=None,
                changelog_latest=None,
                limit=None,
                delay=0.1,
                dry_run=True,
            )


class CliBroadcastTests(unittest.TestCase):
    @patch("app.ops.cli.broadcast_ops.run_broadcast", return_value=0)
    def test_cli_requires_confirm_without_dry_run(self, mocked_run):
        with redirect_stdout(StringIO()):
            code = cli.main(["broadcast", "--audience", "approved", "--text", "hi"])
        self.assertEqual(code, 2)
        mocked_run.assert_not_called()

    @patch("app.ops.cli.broadcast_ops.run_broadcast", return_value=0)
    def test_cli_broadcast_dry_run(self, mocked_run):
        code = cli.main(["broadcast", "--audience", "approved", "--text", "hi", "--dry-run"])
        self.assertEqual(code, 0)
        mocked_run.assert_called_once()
        kwargs = mocked_run.call_args.kwargs
        self.assertTrue(kwargs["dry_run"])


class CliGovernanceTests(unittest.TestCase):
    @patch("app.ops.cli.governance_ops.print_governance_checks", return_value=0)
    def test_cli_governance_checks(self, mocked_checks):
        code = cli.main(["governance", "checks", "--branch", "main"])
        self.assertEqual(code, 0)
        mocked_checks.assert_called_once_with(branch="main")


class CliPlannerAndAlertsTests(unittest.TestCase):
    @patch("app.ops.cli.backup_planner_ops.install_backup_timer")
    def test_cli_backup_schedule_enable(self, mocked_install):
        mocked_install.return_value = (Path("/tmp/svc"), Path("/tmp/timer"))
        with redirect_stdout(StringIO()):
            code = cli.main(
                [
                    "backup",
                    "schedule-enable",
                    "--time",
                    "03:15",
                    "--retain",
                    "15",
                    "--scope",
                    "user",
                ]
            )
        self.assertEqual(code, 0)
        mocked_install.assert_called_once_with(time_hhmm="03:15", retain=15, scope="user")

    @patch("app.ops.cli.alerts_ops.send_alert", return_value=(1, []))
    def test_cli_alerts_test(self, mocked_send):
        with redirect_stdout(StringIO()):
            code = cli.main(["alerts", "test", "--message", "hello"])
        self.assertEqual(code, 0)
        mocked_send.assert_called_once_with("hello")

    @patch("app.ops.cli.monitor_ops.run_monitor_check", return_value=0)
    def test_cli_monitor_check_notify(self, mocked_monitor):
        code = cli.main(["monitor", "check", "--notify"])
        self.assertEqual(code, 0)
        mocked_monitor.assert_called_once_with(notify=True)

    @patch("app.ops.cli.monitor_ops.install_event_alerts")
    def test_cli_monitor_events_enable(self, mocked_install):
        mocked_install.return_value = (Path("/tmp/template"), [Path("/tmp/dropin")])
        with redirect_stdout(StringIO()):
            code = cli.main(["monitor", "events-enable", "--scope", "user", "--units", "bot"])
        self.assertEqual(code, 0)
        mocked_install.assert_called_once_with(scope="user", units_csv="bot")

    @patch("app.ops.cli.get_all_users", return_value=[(10, "Тест Т.Т.", "test_user")])
    @patch("app.ops.cli.alerts_ops.load_contacts", return_value=[10])
    def test_cli_alerts_contacts_list_prints_names(self, _mock_contacts, _mock_users):
        out = StringIO()
        with redirect_stdout(out):
            code = cli.main(["alerts", "contacts", "list"])
        self.assertEqual(code, 0)
        value = out.getvalue()
        self.assertIn("Тест Т.Т.", value)
        self.assertIn("@test_user", value)

    @patch("app.ops.cli.get_all_users", return_value=[(10, "Тест Т.Т.", "test_user")])
    @patch("app.ops.cli.alerts_ops.load_contacts", return_value=[10])
    def test_cli_alerts_contacts_remove_without_id_shows_current(self, _mock_contacts, _mock_users):
        out = StringIO()
        with redirect_stdout(out):
            code = cli.main(["alerts", "contacts", "remove"])
        self.assertEqual(code, 2)
        value = out.getvalue()
        self.assertIn("Текущие техадмины", value)
        self.assertIn("Тест Т.Т.", value)

    @patch("app.ops.cli.alerts_ops.send_alert", return_value=(1, []))
    @patch("app.ops.cli.alerts_ops.build_event_alert_text", return_value="event text")
    def test_cli_alerts_event(self, mocked_build, mocked_send):
        with redirect_stdout(StringIO()):
            code = cli.main(["alerts", "event", "--unit", "telegram_bot.service", "--scope", "system"])
        self.assertEqual(code, 0)
        mocked_build.assert_called_once_with(unit="telegram_bot.service", scope="system")
        mocked_send.assert_called_once_with("event text")


class BackupOpsTests(unittest.TestCase):
    def test_verify_backup_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sample.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO t DEFAULT VALUES")
                conn.commit()

            checked, is_ok, result = backup_ops.verify_backup(db_path)
            self.assertEqual(checked, db_path)
            self.assertTrue(is_ok)
            self.assertEqual(result.lower(), "ok")

    def test_restore_backup_creates_safety_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_backup = tmp_path / "source.db"
            target_db = tmp_path / "target.db"
            backup_dir = tmp_path / "backups"

            with sqlite3.connect(source_backup) as conn:
                conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
                conn.execute("INSERT INTO t (val) VALUES ('from_backup')")
                conn.commit()

            with sqlite3.connect(target_db) as conn:
                conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
                conn.execute("INSERT INTO t (val) VALUES ('old_data')")
                conn.commit()

            with patch.object(backup_ops, "BACKUP_DIR", backup_dir), patch.object(
                backup_ops, "resolve_db_path", return_value=target_db
            ):
                restored, safety = backup_ops.restore_backup(source_backup)

            self.assertEqual(restored, target_db)
            self.assertIsNotNone(safety)
            self.assertTrue(safety.exists())

            with sqlite3.connect(target_db) as conn:
                value = conn.execute("SELECT val FROM t LIMIT 1").fetchone()[0]
            self.assertEqual(value, "from_backup")


class RunOpsTests(unittest.TestCase):
    def test_background_start_status_stop_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pid_dir = tmp_path / "pids"
            log_dir = tmp_path / "logs"
            components = {"test": [sys.executable, "-c", "import time; time.sleep(30)"]}

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                with patch.object(run_ops, "PID_DIR", pid_dir), patch.object(
                    run_ops, "LOG_DIR", log_dir
                ), patch.object(run_ops, "RUN_COMPONENTS", components):
                    pid, _log_path = run_ops.start_component_background("test")
                    running, status_pid, _ = run_ops.get_component_background_status("test")
                    self.assertTrue(running)
                    self.assertEqual(pid, status_pid)

                    stopped = run_ops.stop_component_background("test", force=True)
                    self.assertTrue(stopped)
                    running_after, _, _ = run_ops.get_component_background_status("test")
                    self.assertFalse(running_after)


if __name__ == "__main__":
    unittest.main()
