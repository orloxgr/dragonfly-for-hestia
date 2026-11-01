"""Render the actual owner view using synthetic data and no hosting accounts."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
NATIVE_PHP=Path('/usr/local/hestia/php/bin/php')
PHP=str(NATIVE_PHP) if NATIVE_PHP.is_file() else shutil.which('php')


@unittest.skipUnless(PHP, 'PHP is required for view rendering')
class ConnectionView(unittest.TestCase):
    def render(self, selected='two.example', empty=False):
        sites=[] if empty else [dict(domain=name, aliases=[], enabled=True, suspended=False, prefix=prefix)
            for name,prefix in [('one.example','dfh:example:first:'),('two.example','dfh:example:second:')]]
        data=dict(enabled=True, allowed=True, sites=sites, connection=dict(host='127.0.0.1',port=6379,
            username='example_user',password='example_password',database=11))
        with tempfile.TemporaryDirectory(prefix='dragonfly-view-') as directory:
            folder=Path(directory)
            templates=folder/'web/templates'
            templates.mkdir(parents=True)
            (templates/'header.php').write_text('<!doctype html><html><head><meta charset="utf-8">'
                '<link rel="stylesheet" href="/css/themes/default.min.css">'
                '<link rel="stylesheet" href="/css/themes/dark.min.css"></head><body>',encoding='utf-8')
            (templates/'footer.php').write_text('</body></html>',encoding='utf-8')
            harness=folder/'render.php'
            harness.write_text('''<?php
error_reporting(E_ALL);
$root=getenv('FIXTURE_ROOT'); $headerOwner='example'; $owner='example'; $TAB='WEB';
function top_panel($owner,$tab) { return []; }
$meta=['title'=>'Dragonfly for Hestia','version'=>'test'];
$data=json_decode(getenv('FIXTURE_DATA'),true);
$selectedDomain=getenv('FIXTURE_DOMAIN');
$isAdmin=false; $managed=true; $pageError=''; $message=''; $messageType='success';
$escape=static fn($s)=>htmlspecialchars((string)$s,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');
$formFields=static function($action,$domain=null) {};
require getenv('FIXTURE_VIEW');
''',encoding='utf-8')
            result=subprocess.run([PHP,'-d','display_errors=stderr',str(harness)],capture_output=True,encoding='utf-8',
                env={**os.environ,'FIXTURE_ROOT':str(folder),'FIXTURE_DATA':json.dumps(data),
                     'FIXTURE_DOMAIN':selected,'FIXTURE_VIEW':str(ROOT/'panel/view.php')})
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stderr,'')
            return result.stdout

    def test_selected_website_prefix_and_all_credentials_are_in_one_section(self):
        body=self.render()
        section=re.search(r'<section[^>]+id="connection-details".*?</section>',body,re.S)[0]
        for field in ['site','prefix','host','port','username','password','database']:
            self.assertIn('id="connection-'+field+'"',section)
        self.assertIn('value="two.example" data-cache-prefix="dfh:example:second:" selected',section)
        self.assertIn('id="connection-prefix" type="text" value="dfh:example:second:"',section)
        self.assertEqual(body.count('id="connection-prefix"'),1)
        if os.environ.get('VIEW_PREVIEW_OUTPUT'):
            Path(os.environ['VIEW_PREVIEW_OUTPUT']).write_text(body,encoding='utf-8')

    def test_other_site_and_unknown_selection_resolve_to_an_owned_prefix(self):
        for selected in ['one.example','foreign.example']:
            body=self.render(selected)
            self.assertIn('id="connection-prefix" type="text" value="dfh:example:first:"',body)
            self.assertNotIn('value="foreign.example"',body)

    def test_account_without_websites_keeps_account_credentials_without_fake_prefix(self):
        body=self.render(empty=True)
        self.assertIn('id="connection-username"',body)
        self.assertNotIn('id="connection-prefix"',body)
        self.assertNotIn('id="connection-site"',body)


if __name__=='__main__':
    unittest.main()
