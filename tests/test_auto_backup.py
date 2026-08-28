import unittest
from datetime import datetime, timedelta

from app import _auto_backup_due, reset_user_current_traffic


class AutoBackupDueTest(unittest.TestCase):
    def test_disabled_is_not_due(self):
        self.assertFalse(_auto_backup_due({'enabled': False, 'interval_hours': 1}))

    def test_enabled_with_no_last_run_is_due(self):
        self.assertTrue(_auto_backup_due({'enabled': True, 'interval_hours': 24}))

    def test_invalid_last_run_is_due(self):
        self.assertTrue(_auto_backup_due({
            'enabled': True,
            'interval_hours': 24,
            'last_run_at': 'not-a-timestamp',
        }))

    def test_not_due_before_interval_elapses(self):
        now = datetime(2026, 8, 28, 12, 0, 0)
        last = (now - timedelta(hours=1)).isoformat()
        self.assertFalse(_auto_backup_due({
            'enabled': True,
            'interval_hours': 24,
            'last_run_at': last,
        }, now=now))

    def test_due_after_interval_elapses(self):
        now = datetime(2026, 8, 28, 12, 0, 0)
        last = (now - timedelta(hours=24)).isoformat()
        self.assertTrue(_auto_backup_due({
            'enabled': True,
            'interval_hours': 24,
            'last_run_at': last,
        }, now=now))

    def test_invalid_interval_falls_back_to_24h(self):
        now = datetime(2026, 8, 28, 12, 0, 0)
        last = (now - timedelta(hours=12)).isoformat()
        self.assertFalse(_auto_backup_due({
            'enabled': True,
            'interval_hours': 'nope',
            'last_run_at': last,
        }, now=now))


class ResetUserCurrentTrafficTest(unittest.TestCase):
    def test_zeros_current_usage_and_keeps_totals(self):
        now = datetime(2026, 8, 28, 12, 0, 0)
        user = {
            'traffic_used': 12345,
            'traffic_total': 99999,
            'last_reset_at': '2026-01-01T00:00:00',
        }
        reset_user_current_traffic(user, now=now)
        self.assertEqual(user['traffic_used'], 0)
        self.assertEqual(user['traffic_total'], 99999)
        self.assertEqual(user['last_reset_at'], now.isoformat())


if __name__ == '__main__':
    unittest.main()
