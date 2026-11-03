import contextlib
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import addon
from errors import OperationError
from resp import Client,RedisError

class StartupErrors(unittest.TestCase):
    def test_loading_code_survives_without_disclosing_the_server_message(self):
        client=object.__new__(Client)
        client.file=io.BytesIO(b'-LOADING confidential-server-detail\r\n')
        with self.assertRaises(RedisError) as caught:client.read()
        self.assertEqual(caught.exception.code,'LOADING')
        self.assertNotIn('confidential',str(caught.exception))

    def test_unknown_errors_do_not_expose_native_message_as_a_code(self):
        client=object.__new__(Client)
        client.file=io.BytesIO(b'-private-credential confidential-server-detail\r\n')
        with self.assertRaises(RedisError) as caught:client.read()
        self.assertIsNone(caught.exception.code)
        self.assertNotIn('private',str(caught.exception))

    @unittest.skipUnless(os.name=='posix' and os.geteuid()==0,'Linux root bridge fixture')
    def test_bridge_exposes_only_controlled_operational_messages(self):
        for error in (OperationError('resize_recovery_pending','Controlled recovery message'),RuntimeError('confidential-server-detail')):
            output=io.StringIO()
            with patch.object(addon.sys,'argv',['bridge']),patch.object(addon.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(b'{}'))), \
                 patch.object(addon,'dispatch',side_effect=error),contextlib.redirect_stdout(output):
                self.assertEqual(addon.locked_main(),1)
            value=json.loads(output.getvalue())
            self.assertNotIn('confidential',output.getvalue())
            if isinstance(error,OperationError):self.assertEqual(value['error_code'],'resize_recovery_pending')
