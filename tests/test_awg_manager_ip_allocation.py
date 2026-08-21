import unittest

from managers.awg_manager import AWGManager


class AWGManagerIpAllocationTest(unittest.TestCase):
    def make_manager(self, subnet, used_ips):
        manager = AWGManager.__new__(AWGManager)
        manager._get_subnet_base = lambda protocol: subnet
        manager._get_used_ips = lambda protocol: list(used_ips)
        return manager

    def test_get_next_ip_returns_first_free_host_in_subnet(self):
        manager = self.make_manager('10.8.0.0/30', ['10.8.0.1'])

        self.assertEqual(manager._get_next_ip('awg'), '10.8.0.2')

    def test_get_next_ip_raises_when_subnet_exhausted(self):
        manager = self.make_manager('10.8.0.0/30', ['10.8.0.1', '10.8.0.2'])

        with self.assertRaises(RuntimeError):
            manager._get_next_ip('awg')

    def test_get_next_ip_skips_non_contiguous_used_ips(self):
        manager = self.make_manager('10.8.0.0/24', ['10.8.0.1', '10.8.0.5', '10.8.0.10'])

        self.assertEqual(manager._get_next_ip('awg'), '10.8.0.2')

    def test_get_next_ip_skips_gateway_dot_one(self):
        manager = self.make_manager('10.8.0.0/24', ['10.8.0.1'])

        self.assertEqual(manager._get_next_ip('awg'), '10.8.0.2')

    def test_get_next_ip_raises_when_all_hosts_exhausted_in_small_subnet(self):
        manager = self.make_manager('10.8.0.0/30', ['10.8.0.1', '10.8.0.2'])

        with self.assertRaises(RuntimeError):
            manager._get_next_ip('awg')

    def test_get_next_ip_with_empty_used_ips(self):
        manager = self.make_manager('10.8.0.0/24', [])

        self.assertEqual(manager._get_next_ip('awg'), '10.8.0.1')

    def test_get_next_ip_with_subnet_missing_mask(self):
        manager = AWGManager.__new__(AWGManager)
        manager._get_subnet_base = lambda protocol: '10.8.1.0'
        manager._get_subnet_cidr = lambda protocol: '24'
        manager._get_used_ips = lambda protocol: []

        self.assertEqual(manager._get_next_ip('awg'), '10.8.1.1')


if __name__ == '__main__':
    unittest.main()
