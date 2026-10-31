#!/usr/bin/python3
"""Install the independent addon, or explicitly adopt an existing Dragonfly."""
import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import traceback
import urllib.request

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'src'))
from addon import hestia
from files import write,write_json,ensure_owned_directory,sync_directory
from inventory import collect
from registry import desired_state
import service
import deployment
from resp import Client,text

VERSION = '2.0.2'
SHA256 = '348132783a88e0a18ff2f3748523444957f139d2b9165ac759c84400c9010902'
PACKAGE_URL = 'https://github.com/dragonflydb/dragonfly/releases/download/v2.0.2/dragonfly_amd64.deb'
DROPIN = Path('/etc/systemd/system/dragonfly.service.d/30-hestia-dragonfly.conf')
CRON = Path('/etc/cron.d/dragonfly-for-hestia')
PENDING = service.STORE/'install.json'
RECEIPT = service.STORE/'install-receipt.json'


def run(*args,**options):
    result = subprocess.run(args,capture_output=True,timeout=600,**options)
    if result.returncode:
        for label, output in (('stdout', result.stdout), ('stderr', result.stderr)):
            if output:
                text = output.decode(errors='replace') if isinstance(output, bytes) else output
                sys.stderr.write(label + ':\n' + text.rstrip() + '\n')
        raise RuntimeError('Command failed (exit ' + str(result.returncode) + '): ' + shlex.join(args))
    return result


def install_package():
    cache = Path('/var/cache/dragonfly-for-hestia')
    cache.mkdir(mode=0o755,parents=True,exist_ok=True)
    package = cache/'dragonfly_amd64.deb'
    if not package.exists() or hashlib.sha256(package.read_bytes()).hexdigest() != SHA256:
        request = urllib.request.Request(PACKAGE_URL,headers={'User-Agent':'dragonfly-for-hestia'})
        with urllib.request.urlopen(request,timeout=120) as response:
            data = response.read(150*1024*1024)
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise ValueError('Official package checksum mismatch')
        package.write_bytes(data);package.chmod(0o644)
    env = dict(os.environ,DEBIAN_FRONTEND='noninteractive')
    run('apt-get','update','-o','APT::Update::Error-Mode=any',env=env)
    run('apt-get','install','-y',str(package),env=env)


def validate_binary():
    result = run('/usr/bin/dragonfly','--version').stdout.decode(errors='replace')
    result = re.sub(r'\x1b\[[0-9;]*m','',result)
    if not re.search(r'\bv'+re.escape(VERSION)+r'(?:-|\b)',result):
        raise ValueError('This addon release supports Dragonfly '+VERSION)


def adopt(state, manifest, config):
    imported = manifest['owners']
    if not isinstance(imported,dict) or set(imported)-set(state['owners']):
        raise ValueError('Manifest contains an unknown Hestia owner')
    slots = set()
    for name,row in imported.items():
        if row['database'] in slots:
            raise ValueError('Database collision in adoption manifest')
        slots.add(row['database'])
        if set(row['sites']) != set(state['owners'][name]['sites']):
            raise ValueError('Manifest must describe all sites of an imported owner')
        owner = state['owners'][name]
        owner.update(username=row['username'],password=row['password'],database=row['database'])
        for domain,prefix in row['sites'].items():
            owner['sites'][domain]['prefix'] = prefix
    for name,owner in state['owners'].items():
        if name not in imported:
            slot = next(i for i in range(len(slots)+1) if i not in slots)
            slots.add(slot);owner['database'] = slot
    state['required_database_capacity'] = max(16,1 << max(slots,default=0).bit_length())
    service.validate(state,config)
    with Client(config['admin_password'],port=config['port']) as connection:
        actual = {text(u) for u in connection.command('ACL','USERS')}
        expected = {'default',*(row['username'] for row in imported.values())}
        if actual != expected:
            raise ValueError('Adoption must account for all existing ACL identities')
        info = text(connection.command('INFO','keyspace'))
        occupied = {int(m[0]) for m in re.findall(r'^db(\d+):keys=(\d+)',info,re.M) if int(m[1])}
        if occupied - {row['database'] for row in imported.values()}:
            raise ValueError('Existing data outside the adopted database scopes')
    for name,row in imported.items():
        with Client(row['password'],row['username'],config['port']) as connection:
            connection.command('SELECT',row['database'])


def initialize(args):
    manifest = None
    installed = Path('/usr/bin/dragonfly').is_file()
    if installed and not args.adopt:
        raise ValueError('Existing Dragonfly requires --adopt with a private complete manifest')
    if args.adopt:
        path = Path(args.adopt)
        if not installed or path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
            raise ValueError('Adoption needs an installed service and a root-owned mode-600 manifest')
        validate_binary();manifest = json.loads(path.read_text())
    elif args.port != 6379:
        raise ValueError('Initial release supports the native port 6379')
    if not installed:
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1',args.port))
            except OSError:
                raise ValueError('Port is already in use; refusing to replace another service') from None
    state = desired_state(None,collect(hestia),'dragonfly')
    config = {'schema':1,'installed':False,'version':VERSION,'port':args.port,
              'admin_password':manifest['admin_password'] if manifest else secrets.token_urlsafe(32),
              'maxmemory':(args.memory_mb or 512)*1024*1024,'threads':2,'minimum_databases':256,
              'allowed_packages':None,'denied_packages':[],'adopted':bool(manifest)}
    if manifest:
        if manifest.get('port',6379) != args.port:
            raise ValueError('Adoption endpoint does not match the selected port')
        adopt(state,manifest,config)
    service.validate(state,config)
    if DROPIN.exists() or CRON.exists():
        raise ValueError('Unmanaged addon integration files already exist')
    service.STORE.mkdir(mode=0o700,parents=True,exist_ok=True);service.STORE.chmod(0o700)
    ensure_owned_directory(service.CONFIG,'dragonfly-for-hestia')
    record = {'schema':1,'addon':'dragonfly-for-hestia','state':state,'config':config,'native_existed':installed}
    write_json(PENDING,record)
    return record


def install(args):
    if os.geteuid() != 0:
        raise ValueError('Run this installer as root')
    release = dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID','').strip('"') != 'ubuntu' or release.get('VERSION_ID','').strip('"') != '26.04':
        raise ValueError('Supported operating system: Ubuntu 26.04 amd64')
    if os.uname().machine != 'x86_64':
        raise ValueError('Supported architecture: amd64')
    if not Path('/usr/local/hestia/web/inc/main.php').is_file():
        raise ValueError('Install Hestia before this addon')
    version = run('dpkg-query','-W','-f=${Version}','hestia').stdout.decode().strip()
    if version.split('-')[0] != '1.10.5':
        raise ValueError('This release is verified with Hestia 1.10.5')
    if not PENDING.exists() and (service.CONFIG/'settings.json').exists() and service.settings().get('installed'):
        if args.memory_mb is not None and args.memory_mb*1024*1024 != service.settings()['maxmemory']:
            raise ValueError('Existing memory budget is preserved; change maxmemory in settings.json and reconcile')
        validate_binary()
        try:
            run('python3',str(SOURCE/'tools/install-integration.py'))
            service.reconcile(hestia)
        except Exception:
            deployment.rollback()
            raise
        deployment.commit()
        print(json.dumps({'ok':True,'mode':'upgrade-or-reinstall','credentials_preserved':True}))
        return
    resumed = PENDING.exists()
    if resumed:
        info=PENDING.stat()
        if PENDING.is_symlink() or info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError('Unexpected pending installation')
        record=json.loads(PENDING.read_text())
        if record.get('schema') != 1 or record.get('addon') != 'dragonfly-for-hestia':
            raise ValueError('Unrecognized pending installation')
        if args.memory_mb is not None and args.memory_mb*1024*1024 != record['config']['maxmemory']:
            raise ValueError('Interrupted installation retains its original memory budget')
        ensure_owned_directory(service.CONFIG,'dragonfly-for-hestia')
        for path in (DROPIN,CRON):
            if path.is_symlink() or (path.exists() and '# Managed by dragonfly-for-hestia' not in path.read_text()):
                raise ValueError('Refusing unmanaged integration files')
    else:
        record=initialize(args)
    state=desired_state(record['state'],collect(hestia),'dragonfly')
    config=record['config']; config['installed']=False
    installed=record['native_existed']
    manifest=config['adopted']
    record['state']=state; record['config']=config
    write_json(PENDING,record)
    old_desired = service.STORE/'desired.json'
    backup = service.STORE/'before-install'
    backup.mkdir(mode=0o700,exist_ok=True)
    if old_desired.exists():
        write(backup/'desired.json',old_desired.read_bytes())
    write_json(service.CONFIG/'settings.json',config)
    capacity = max(config['minimum_databases'],state['required_database_capacity'])
    try:
        gid = grp.getgrnam('dfly').gr_gid
    except KeyError:
        gid = 0
    # Before package auto-start, authentication and loopback binding are already
    # configured. The temporary ACL contains hashes only; tighten group mode
    # immediately after the package creates its native dfly group.
    write(service.CONFIG/'users.acl',service.acl_text(state,config),0o640 if gid else 0o644,gid)
    write(service.CONFIG/'environment',service.environment(config,capacity))
    DROPIN.parent.mkdir(parents=True,exist_ok=True)
    write(DROPIN,'# Managed by dragonfly-for-hestia\n[Service]\nEnvironmentFile='+str(service.CONFIG/'environment')+'\n',0o644)
    try:
        if not installed:
            install_package()
        validate_binary()
        gid = grp.getgrnam('dfly').gr_gid
        os.chown(service.CONFIG,0,gid);service.CONFIG.chmod(0o750)
        os.chown(service.CONFIG/'users.acl',0,gid);(service.CONFIG/'users.acl').chmod(0o640)
        run('systemctl','daemon-reload');run('systemctl','restart','dragonfly')
        service.wait_healthy(config)
        with service.admin(config) as connection:
            connection.command('SELECT',capacity-1)
        for row in state['owners'].values():
            if service.prefixes(row,config):
                with Client(row['password'],row['username'],config['port']) as connection:
                    if connection.command('PING') != 'PONG':
                        raise RuntimeError('Tenant authentication failed')
        write_json(service.STORE/'desired.json',state)
        write_json(service.STORE/'applied.json',state)
        run('python3',str(SOURCE/'tools/install-integration.py'))
        config['installed'] = True
        write_json(service.CONFIG/'settings.json',config)
        write(CRON,'# Managed by dragonfly-for-hestia\nSHELL=/bin/sh\nPATH=/usr/sbin:/usr/bin:/sbin:/bin\n* * * * * root /usr/local/hestia/bin/v-dragonfly-hestia reconcile >/dev/null 2>&1\n',0o644)
        run('systemctl','enable','dragonfly')
        os.replace(PENDING,RECEIPT);sync_directory(service.STORE)
        deployment.commit()
        print(json.dumps({'ok':True,'resumed':resumed,'mode':'adopt' if manifest else 'fresh',
                          'accounts':len(state['owners']),'database_capacity':capacity,
                          'credentials_preserved':bool(manifest)}))
    except Exception:
        DROPIN.unlink(missing_ok=True);CRON.unlink(missing_ok=True)
        config['installed'] = False;write_json(service.CONFIG/'settings.json',config)
        run('systemctl','daemon-reload')
        if installed:
            run('systemctl','restart','dragonfly')
        else:
            run('systemctl','stop','dragonfly')
        if (backup/'desired.json').exists():
            write(old_desired,(backup/'desired.json').read_bytes())
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adopt',metavar='PRIVATE_MANIFEST')
    parser.add_argument('--port',type=int,default=6379,choices=[6379])
    parser.add_argument('--memory-mb',type=int,default=None)
    args = parser.parse_args()
    try:
        if args.memory_mb is not None and not 64 <= args.memory_mb <= 1048576:
            raise ValueError('Choose a cache memory budget of at least 64 MiB')
        from operations import exclusive
        with exclusive():
            install(args)
    except Exception as error:
        # This is the administrator's installer, not a hosting-user response.
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({'ok':False,'error_type':type(error).__name__,
                          'error':str(error)}))
        raise SystemExit(1)
