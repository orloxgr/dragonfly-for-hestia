import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import service
from registry import desired_state
from resp import Client,RedisError,text


@unittest.skipUnless(os.environ.get('HDN_TEST_DRAGONFLY'),'Isolated native Dragonfly')
class NativeACL(unittest.TestCase):
    def test_data_types_work_while_foreign_keys_databases_and_administration_remain_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            config=dict(port=port,threads=1,maxmemory=256*1024*1024,admin_password='native-isolated-proof-password')
            inventory={name:dict(identity=name,package='default',role='user',suspended=False,
                sites={name+'.test':dict(aliases=[],suspended=False)}) for name in ('alice','bob')}
            state=desired_state(None,inventory,'dragonfly')
            with patch.object(service,'CONFIG',root):
                (root/'users.acl').write_text(service.acl_text(state,config))
                env={**os.environ,'DFLY_dir':str(root),'DFLY_logtostderr':'true'}
                env.update(line.split('=',1) for line in service.environment(config,16).splitlines())
            with (root/'native.log').open('wb') as log:
                child=subprocess.Popen([os.environ['HDN_TEST_DRAGONFLY']],env=env,cwd=root,stdout=log,stderr=log)
                try:
                    deadline=time.monotonic()+15
                    while True:
                        try:
                            with Client(config['admin_password'],port=port,timeout=1) as admin:admin.command('PING')
                            break
                        except OSError:
                            if child.poll() is not None or time.monotonic()>deadline:self.fail((root/'native.log').read_text())
                            time.sleep(.05)
                    alice=state['owners']['alice'];bob=state['owners']['bob']
                    with Client(config['admin_password'],port=port) as admin:
                        admin.command('SELECT',alice['database'])
                        admin.command('SET','foreign:secret','hidden')
                    prefix=alice['sites']['alice.test']['prefix']
                    with Client(alice['password'],alice['username'],port=port,timeout=2) as client:
                        client.command('SELECT',alice['database'])
                        for args in [('SETNX',prefix+'string','value'),('HSET',prefix+'hash','field','value'),
                            ('LPUSH',prefix+'list','value'),('SADD',prefix+'set','value'),('ZADD',prefix+'sorted',1,'value')]:
                            client.command(*args)
                        self.assertEqual(text(client.command('HGET',prefix+'hash','field')),'value')
                        self.assertEqual(text(client.command('EVAL',"return redis.call('GET',KEYS[1])",1,prefix+'string')),'value')
                        dumped=client.command('DUMP',prefix+'string')
                        client.command('RESTORE',prefix+'restored',0,dumped)
                        self.assertEqual(text(client.command('GET',prefix+'restored')),'value')
                        for args in [('GET','foreign:secret'),('SET','foreign:secret','value'),('SELECT',bob['database']),
                            ('FLUSHDB',),('FLUSHALL',),('CONFIG','SET','maxmemory','1'),('ACL','LIST'),
                            ('EVAL',"return redis.call('GET','foreign:secret')",0),
                            ('EVAL',"return redis.call('SELECT',ARGV[1])",0,bob['database']),
                            ('EVAL',"return redis.call('FLUSHDB')",0),('RESTORE','foreign:restored',0,dumped)]:
                            with self.subTest(command=args[0]),self.assertRaises(RedisError):client.command(*args)
                finally:
                    child.terminate()
                    try:child.wait(timeout=15)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
