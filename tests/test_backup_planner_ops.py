import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ops import backup_planner_ops


class BackupPlannerOpsTests(unittest.TestCase):
    def test_parse_hhmm(self):
        hour, minute = backup_planner_ops._parse_hhmm("03:45")
        self.assertEqual(hour, 3)
        self.assertEqual(minute, 45)

        with self.assertRaises(ValueError):
            backup_planner_ops._parse_hhmm("99:10")

    def test_install_backup_timer_writes_units_and_calls_systemctl(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            service_target = tmp_path / "service.unit"
            timer_target = tmp_path / "timer.unit"

            def fake_write(unit_name: str, content: str, scope: str):
                self.assertEqual(scope, "user")
                if unit_name.endswith(".service"):
                    service_target.write_text(content, encoding="utf-8")
                    return service_target
                timer_target.write_text(content, encoding="utf-8")
                return timer_target

            with patch("app.ops.backup_planner_ops.write_unit", side_effect=fake_write), patch(
                "app.ops.backup_planner_ops.run_systemctl"
            ) as mocked_systemctl:
                service_path, timer_path = backup_planner_ops.install_backup_timer(
                    time_hhmm="04:10",
                    retain=14,
                    scope="user",
                )

            self.assertEqual(service_path, service_target)
            self.assertEqual(timer_path, timer_target)
            self.assertIn("backup prune --retain 14", service_target.read_text(encoding="utf-8"))
            self.assertIn("OnCalendar=*-*-* 04:10:00", timer_target.read_text(encoding="utf-8"))

            calls = mocked_systemctl.call_args_list
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0].args, ("user", ["daemon-reload"]))
            self.assertEqual(calls[1].args, ("user", ["enable", "--now", backup_planner_ops.BACKUP_TIMER_UNIT]))


if __name__ == "__main__":
    unittest.main()

