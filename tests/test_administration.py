"""Administrator bulk cache scopes and native role authorization."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import administration
import addon


class Administration(unittest.TestCase):
    def setUp(self):
        self.state = {'owners': {name: {'enabled': True, 'password': 'example-password',
            'sites': {name+'.example': {'enabled': True, 'prefix': name+':'}}} for name in ['alice', 'bob']}}

    def test_site_and_account_operations_preserve_credentials_prefixes_and_other_choices(self):
        before = copy.deepcopy(self.state)
        administration.mutate(self.state, {'operation': 'disable-sites', 'scope': 'selected', 'accounts': ['alice']}, 'dragonfly')
        before['owners']['alice']['sites']['alice.example']['enabled'] = False
        self.assertEqual(self.state, before)
        administration.mutate(self.state, {'operation': 'disable-accounts', 'scope': 'all'}, 'dragonfly')
        self.assertTrue(all(not row['enabled'] for row in self.state['owners'].values()))
        self.assertEqual(self.state['owners']['alice']['sites'], before['owners']['alice']['sites'])

    def test_invalid_target_or_profile_leaves_complete_state_unchanged(self):
        before = copy.deepcopy(self.state)
        for payload in [{'operation': 'disable-sites', 'scope': 'selected', 'accounts': ['alice'],
                         'targets': [{'owner': 'alice', 'domain': 'bob.example'}]},
                        {'operation': 'set-profile', 'scope': 'all', 'profile': 'general'},
                        {'operation': 'enable-sites', 'scope': 'selected'}]:
            with self.assertRaises(ValueError):
                administration.mutate(self.state, payload, 'dragonfly')
            self.assertEqual(self.state, before)

    def test_global_actions_require_native_active_admin_role(self):
        for role, suspended in [('user', 'no'), ('admin', 'yes')]:
            with patch.object(addon, 'hestia', return_value={'alice': {'ROLE': role, 'SUSPENDED': suspended}}), \
                 patch.object(administration, 'request') as request:
                with self.assertRaises(addon.RequestError):
                    addon.dispatch({'actor': 'alice', 'owner': 'alice', 'action': 'admin-bulk', 'admin': True})
                request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
