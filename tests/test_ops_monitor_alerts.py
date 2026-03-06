import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from app.ops import alerts_ops, monitor_ops


class AlertsOpsTests(unittest.TestCase):
    def test_add_remove_contacts_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            contacts_file = Path(tmp) / "ops_contacts.json"
            with patch.object(alerts_ops, "CONTACTS_FILE", contacts_file):
                self.assertEqual(alerts_ops.load_contacts(), [])
                contacts = alerts_ops.add_contact(10)
                self.assertEqual(contacts, [10])
                contacts = alerts_ops.add_contact(10)
                self.assertEqual(contacts, [10])
                contacts = alerts_ops.add_contact(20)
                self.assertEqual(contacts, [10, 20])
                contacts = alerts_ops.remove_contact(10)
                self.assertEqual(contacts, [20])


class MonitorOpsTests(unittest.TestCase):
    def test_notifications_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "monitor_state.json"
            incidents = [
                monitor_ops.Incident(
                    severity="critical",
                    source="bot",
                    message="down",
                )
            ]
            with patch.object(monitor_ops, "MONITOR_STATE_FILE", state_file), patch(
                "app.ops.monitor_ops.alerts_ops.load_contacts",
                return_value=[123],
            ), patch(
                "app.ops.monitor_ops.alerts_ops.send_alert",
                return_value=(1, []),
            ) as mocked_send:
                with redirect_stdout(StringIO()):
                    monitor_ops._send_notifications_if_needed(incidents)
                    monitor_ops._send_notifications_if_needed(incidents)

            self.assertEqual(mocked_send.call_count, 1)

    @patch("app.ops.monitor_ops.status_ops.collect_process_statuses")
    @patch("app.ops.monitor_ops.status_ops.collect_systemd_statuses")
    @patch("app.ops.monitor_ops.backup_ops.disk_guardrail_status")
    @patch("app.ops.monitor_ops._is_failed_unit")
    def test_collect_incidents_when_everything_ok(
        self,
        mocked_failed,
        mocked_disk,
        mocked_systemd,
        mocked_processes,
    ):
        mocked_processes.return_value = {"bot": ["pid"], "webapp": ["pid"], "notifications": [], "cloudflared": []}
        mocked_systemd.return_value = {
            "bot": ("active", "enabled", "telegram_bot.service", "system"),
            "webapp": ("active", "enabled", "telegram_webapp.service", "system"),
            "notify-timer": ("active", "enabled", "telegram_bot_notify.timer", "user"),
        }
        mocked_disk.return_value = ("ok", "ok", 100, 1000, 10.0)
        mocked_failed.return_value = False

        incidents = monitor_ops.collect_incidents()
        self.assertEqual(incidents, [])

    def test_parse_units_argument_with_alias(self):
        units = monitor_ops._parse_units_argument("bot,webapp", scope="user")
        self.assertIn("telegram_bot.service", units)
        self.assertIn("telegram_webapp.service", units)

    def test_event_alerts_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dropin = base / "telegram_bot.service.d" / "90-telegram-event-alert.conf"
            dropin.parent.mkdir(parents=True, exist_ok=True)
            dropin.write_text("x", encoding="utf-8")

            with patch("app.ops.monitor_ops.unit_dir", return_value=base):
                rows = monitor_ops.event_alerts_status(scope="system", units_csv="telegram_bot.service")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "telegram_bot.service")
            self.assertTrue(rows[0][1])


if __name__ == "__main__":
    unittest.main()
