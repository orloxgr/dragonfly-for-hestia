"""Shared memory persistence, restart recovery and native Dragonfly proof."""
import contextlib
import copy
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import addon
import administration
import cache_size
import service
import transaction
from registry import desired_state
from resp import Client


class CacheSize(unittest.TestCase):
    @contextlib.contextmanager
    def installation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            config=dict(installed=True,maxmemory=256*cache_size.MIB,port=6379,threads=1,
                        admin_password='A'*32,minimum_databases=16)
            inventory={'alice':dict(identity='one',package='default',role='user',suspended=False,
                                   sites={'example.test':dict(aliases=[],suspended=False)})}
            state=desired_state(None,inventory,'dragonfly')
            for filename in ('desired.json','applied.json'):(root/filename).write_text(json.dumps(state))
            (root/'settings.json').write_text(json.dumps(config))
            (root/'environment').write_text(service.environment(config,16))
            (root/'users.acl').write_text(service.acl_text(state,config))
            with patch.object(service,'CONFIG',root),patch.object(service,'STORE',root), \
                 patch.object(service,'command') as command,patch.object(service,'wait_healthy'), \
                 patch.object(cache_size,'check_budget'):
                yield root,config,state,command

    def test_invalid_size_is_rejected_before_native_operations(self):
        for value in (None,True,'2048',63,1048577,128.5,'64; reboot'):
            with patch.object(service,'recover_pending') as recover:
                with self.assertRaises(ValueError):cache_size.resize(value)
                recover.assert_not_called()

    def test_resize_preserves_accounts_credentials_and_all_other_startup_settings(self):
        with self.installation() as (root,config,state,command):
            before={name:(root/name).read_bytes() for name in ('users.acl','desired.json','applied.json')}
            old_environment=(root/'environment').read_text()
            updated,restarted=cache_size.resize(2048)
            self.assertTrue(restarted);self.assertEqual(updated,{**config,'maxmemory':2048*cache_size.MIB})
            self.assertEqual(service.settings(),updated)
            self.assertEqual((root/'environment').read_text(),old_environment.replace('DFLY_maxmemory=268435456','DFLY_maxmemory=2147483648'))
            for name,data in before.items():self.assertEqual((root/name).read_bytes(),data)
            command.assert_called_once_with('systemctl','restart','dragonfly')
            command.reset_mock();self.assertFalse(cache_size.resize(2048)[1]);command.assert_not_called()
            self.assertFalse((root/cache_size.JOURNAL).exists())

    def test_failed_restart_rolls_back_settings_and_native_environment(self):
        with self.installation() as (root,config,state,command):
            before=(root/'environment').read_bytes()
            with patch.object(service,'wait_healthy',side_effect=[RuntimeError('failed'),None]):
                with self.assertRaisesRegex(RuntimeError,'previous memory limit was restored'):cache_size.resize(512)
            self.assertEqual(service.settings(),config)
            self.assertEqual((root/'environment').read_bytes(),before)
            self.assertEqual(command.call_count,2)
            self.assertFalse((root/cache_size.JOURNAL).exists())

    def test_interrupted_resize_is_recovered_on_next_settings_read(self):
        with self.installation() as (root,config,state,command):
            transaction.begin(root,cache_size.paths(),filename=cache_size.JOURNAL)
            (root/'settings.json').write_text(json.dumps({**config,'maxmemory':512*cache_size.MIB}))
            (root/'environment').write_text('partial startup settings')
            self.assertEqual(service.settings(),config)
            self.assertIn('DFLY_maxmemory=268435456',(root/'environment').read_text())
            command.assert_called_once_with('systemctl','restart','dragonfly')

    def test_failed_recovery_retains_undo_record_until_retry_succeeds(self):
        with self.installation() as (root,config,state,command):
            with patch.object(service,'wait_healthy',side_effect=RuntimeError('failed')):
                with self.assertRaisesRegex(RuntimeError,'recovery is pending'):cache_size.resize(512)
            self.assertTrue((root/cache_size.JOURNAL).exists())
            self.assertEqual(service.settings(),config)
            self.assertFalse((root/cache_size.JOURNAL).exists())

    def test_foreign_startup_memory_value_is_not_overwritten(self):
        with self.installation() as (root,config,state,command):
            (root/'environment').write_text('DFLY_maxmemory=1\n')
            with self.assertRaisesRegex(ValueError,'differs from the saved'):cache_size.resize(512)
            command.assert_not_called()

    def test_native_thread_minimum_is_checked_before_writing_or_restarting(self):
        with self.installation() as (root,config,state,command):
            (root/'settings.json').write_text(json.dumps({**config,'threads':2}))
            before=(root/'environment').read_bytes()
            with self.assertRaisesRegex(ValueError,'per configured worker'):cache_size.resize(256)
            self.assertEqual((root/'environment').read_bytes(),before)
            self.assertFalse((root/cache_size.JOURNAL).exists());command.assert_not_called()

    def test_admin_form_reports_budget_without_account_mutations_or_stats_polling(self):
        with self.installation() as (root,config,state,command),patch.object(service,'reconcile') as reconcile:
            result=administration.request(None,'admin-memory-size',{'memory_mb':512},'dragonfly')
            self.assertEqual(result['memory_budget_mb'],512)
            self.assertTrue(result['service_restarted']);self.assertTrue(result['memory_size_saved'])
            self.assertEqual(result['total_sites'],1);reconcile.assert_not_called()

    def test_native_role_checks_reject_users_and_suspended_administrators(self):
        for role,suspended in [('user','no'),('admin','yes')]:
            with patch.object(addon,'hestia',return_value={'alice':{'ROLE':role,'SUSPENDED':suspended}}), \
                 patch.object(administration,'request') as request:
                with self.assertRaises(addon.RequestError):addon.dispatch(dict(actor='alice',owner='alice',action='admin-memory-size',memory_mb=128,admin=True))
                request.assert_not_called()


@unittest.skipUnless(os.environ.get('HDN_TEST_DRAGONFLY'),'Native isolated Dragonfly process')
class NativeBudget(unittest.TestCase):
    def test_restart_applies_budget_and_preserves_tenant_authentication(self):
        with tempfile.TemporaryDirectory(prefix='dfh-budget-') as folder:
            root=Path(folder)
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            config=dict(installed=True,maxmemory=256*cache_size.MIB,port=port,threads=1,admin_password=secrets.token_urlsafe(32),minimum_databases=16)
            inventory={'alice':dict(identity='one',package='default',role='user',suspended=False,
                                   sites={'example.test':dict(aliases=[],suspended=False)})}
            state=desired_state(None,inventory,'dragonfly');owner=state['owners']['alice']
            process=None
            with patch.object(service,'CONFIG',root),patch.object(service,'STORE',root):
                (root/'settings.json').write_text(json.dumps(config))
                (root/'environment').write_text(service.environment(config,16))
                (root/'users.acl').write_text(service.acl_text(state,config))
                for filename in ('desired.json','applied.json'):(root/filename).write_text(json.dumps(state))
                def stop():
                    nonlocal process
                    if process is not None:
                        if process.poll() is None:process.terminate()
                        try:process.communicate(timeout=8)
                        except subprocess.TimeoutExpired:process.kill();process.communicate()
                        process=None
                def restart(*args):
                    nonlocal process
                    self.assertEqual(args,('systemctl','restart','dragonfly'));stop()
                    env={**os.environ,'DFLY_dir':str(root),'DFLY_logtostderr':'true'}
                    env.update(line.split('=',1) for line in (root/'environment').read_text().splitlines())
                    process=subprocess.Popen([os.environ['HDN_TEST_DRAGONFLY']],env=env,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                    time.sleep(.15)
                    if process.poll() is not None:
                        output=process.communicate()[1].decode(errors='replace')
                        for value in (config['admin_password'],owner['password']):output=output.replace(value,'[redacted]')
                        raise RuntimeError('Isolated Dragonfly failed to start: '+output[-2500:])
                try:
                    restart('systemctl','restart','dragonfly');service.wait_healthy(config);cache_size.check_budget(config)
                    with Client(owner['password'],owner['username'],port) as connection:self.assertEqual(connection.command('PING'),'PONG')
                    before=(root/'users.acl').read_bytes()
                    with patch.object(service,'command',side_effect=restart):
                        updated,restarted=cache_size.resize(512)
                    self.assertTrue(restarted);cache_size.check_budget(updated)
                    with Client(owner['password'],owner['username'],port) as connection:self.assertEqual(connection.command('PING'),'PONG')
                    self.assertEqual((root/'users.acl').read_bytes(),before)
                    self.assertEqual(updated['admin_password'],config['admin_password'])
                finally:stop()
