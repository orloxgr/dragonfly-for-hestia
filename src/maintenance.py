"""Root-only configuration backup, cold restore and independent addon removal."""
import copy
import datetime
import grp
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

from files import write, write_json, ensure_owned_directory
from inventory import collect
from registry import desired_state, locked_store
from resp import Client, text
import service
import deployment
import transaction

ID = 'dragonfly-for-hestia'
INSTALL = Path('/opt') / ID
ROUTE = Path('/usr/local/hestia/web/plugins/dragonfly')
BRIDGE = Path('/usr/local/hestia/bin/v-dragonfly-hestia')
DROPIN = Path('/etc/systemd/system/dragonfly.service.d/30-hestia-dragonfly.conf')
CRON = Path('/etc/cron.d') / ID


def root_only():
    if os.geteuid() != 0 or os.environ.get('SUDO_USER') == 'hestiaweb':
        raise ValueError('This maintenance command requires an administrator root shell')


def private_path(value):
    path = Path(value)
    if not path.is_absolute() or path.name in ('.', '..'):
        raise ValueError('Use an absolute private backup path')
    parent = path.parent
    if parent.resolve() != parent or parent.is_symlink():
        raise ValueError('Backup parent must not contain symlinks')
    info = parent.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('Backup parent must be root-owned and mode 700')
    for managed in (service.CONFIG, service.STORE, INSTALL, ROUTE):
        if path.is_relative_to(managed):
            raise ValueError('Keep backups outside addon-owned directories')
    return path


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def backup(value):
    root_only()
    destination = private_path(value)
    service.recover_pending()
    with locked_store(service.STORE):
        config = service.effective_config()
        state = json.loads((service.STORE / 'desired.json').read_text())
        service.validate(state, config)
        payload = {'settings': config, 'desired': state}
        archive = {'schema': 1, 'addon': ID, 'service_version': service.binary_version(),
                   'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'cache_data_included': False, 'payload': payload, 'sha256': digest(payload)}
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(archive, stream, sort_keys=True, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    return {'ok': True, 'operation': 'backup', 'accounts': len(state['owners']), 'cache_data_included': False}


def read_backup(value):
    source = private_path(value)
    if source.is_symlink():
        raise ValueError('Backup must be a regular private file')
    info = source.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('Backup must be root-owned, private')
    archive = json.loads(source.read_text())
    if (archive.get('schema') != 1 or archive.get('addon') != ID or
            archive.get('sha256') != digest(archive['payload'])):
        raise ValueError('Unsupported or damaged addon backup')
    payload = archive['payload']
    if payload['desired'].get('kind') != 'dragonfly' or payload['desired'].get('schema') != 1:
        raise ValueError('Unsupported desired state in backup')
    service.validate(payload['desired'], payload['settings'])
    return payload


def owned_directory(path, marker):
    if path.is_symlink() or path.resolve() != path:
        raise ValueError('Unexpected addon directory')
    if path.exists() and (not (path / marker).is_file() or
                          (path / marker).read_text().strip() != ID):
        raise ValueError('Refusing an unmanaged addon directory')


def check_integration():
    deployment.check()
    owned_directory(ROUTE, '.addon-owner')
    owned_directory(service.CONFIG, '.addon-owner')
    for path in (BRIDGE, DROPIN, CRON):
        if path.is_symlink() or (path.exists() and '# Managed by ' + ID not in path.read_text()):
            raise ValueError('Refusing an unmanaged integration file')


def integration_files(source):
    subprocess.run(['python3', str(source / 'tools/install-integration.py')], check=True,
                   capture_output=True, timeout=None)
    DROPIN.parent.mkdir(parents=True, exist_ok=True)
    write(DROPIN, '# Managed by ' + ID + '\n[Service]\nEnvironmentFile=' + str(service.CONFIG / 'environment') + '\n', 0o644)
    write(CRON, '# Managed by ' + ID + '\nSHELL=/bin/sh\nPATH=/usr/sbin:/usr/bin:/sbin:/bin\n'
          '* * * * * root /usr/local/hestia/bin/v-dragonfly-hestia reconcile >/dev/null 2>&1\n', 0o644)



def restore_paths():
    return [service.CONFIG/name for name in ('settings.json','environment','users.acl')] + [
        service.STORE/name for name in ('desired.json','applied.json')] + [DROPIN,CRON]


def recover_restore():
    record=transaction.read(service.STORE,restore_paths(),filename='restore.json')
    if record is None:return
    extra=record['extra']
    service.command('systemctl','stop','dragonfly')
    transaction.restore_files(record)
    service.command('systemctl','daemon-reload')
    if extra['installed']:
        service.command('systemctl','reset-failed','dragonfly')
        service.command('systemctl','start','dragonfly');service.wait_healthy(extra['config'])
        deployment.rollback()
    else:
        for path in (ROUTE,service.CONFIG):
            if path.exists():shutil.rmtree(path)
        deployment.remove()
        for path in service.STORE.iterdir():
            if path.name not in ('registry.lock','restore.json') and path.is_file():path.unlink()
    transaction.finish(service.STORE,filename='restore.json')


def restore(value, hestia, source):
    root_only()
    payload = read_backup(value)
    recover_restore()
    service.recover_pending()
    check_integration()
    if not Path('/usr/bin/dragonfly').is_file():
        raise ValueError('Install the supported Dragonfly package before restoring')
    native_version = service.binary_version()
    # A restored Hestia account can have a different native directory birth time.
    # This explicit root operation rebinds archived identities by Hestia username.
    inventory = collect(hestia)
    archived = copy.deepcopy(payload['desired'])
    for name, row in archived['owners'].items():
        if name in inventory:
            row['identity'] = inventory[name]['identity']
    state = desired_state(archived, inventory, 'dragonfly')
    config = copy.deepcopy(payload['settings'])
    config['installed'] = True
    config['version'] = native_version
    service.validate(state, config)
    installed = (service.CONFIG / 'settings.json').is_file() and service.settings().get('installed')
    if not installed and subprocess.run(['systemctl', 'is-active', '--quiet', 'dragonfly']).returncode == 0:
        raise ValueError('Refusing to replace an active unmanaged Dragonfly')
    old_config = service.settings() if installed else None
    current = json.loads((service.STORE / 'desired.json').read_text()) if installed else None
    if not installed and service.STORE.exists() and any(p.name != 'registry.lock' for p in service.STORE.iterdir()):
        raise ValueError('Refusing unmanaged existing addon state')
    ensure_owned_directory(service.CONFIG, ID)
    service.STORE.mkdir(mode=0o700, parents=True, exist_ok=True)
    write(service.CONFIG / '.addon-owner', ID + '\n', 0o644)
    gid = grp.getgrnam('dfly').gr_gid
    os.chown(service.CONFIG, 0, gid); service.CONFIG.chmod(0o750)
    paths = [service.CONFIG / name for name in ('settings.json', 'environment', 'users.acl')]
    paths += [service.STORE / name for name in ('desired.json', 'applied.json')]
    paths += [DROPIN, CRON]
    before = {p: p.read_bytes() if p.is_file() else None for p in paths}
    with locked_store(service.STORE):
        transaction.begin(service.STORE,restore_paths(),{'installed':bool(installed),'config':old_config},filename='restore.json')
        try:
            if installed:
                # Revoke tenant sessions first. Clearing all addon DBs prevents
                # restoring a former assignment over another owner's cache data.
                with service.admin(old_config) as connection:
                    for username in {row['username'] for row in current['owners'].values()}:
                        connection.command('ACL', 'DELUSER', username)
                service.command('systemctl', 'stop', 'dragonfly')
            else:
                # No tenant was active, but native persisted data could still
                # contain a previous assignment. Start with every tenant off,
                # then clear all databases before enabling the restored ACLs.
                pass
            capacity = max(256, config.get('minimum_databases', 256), state['required_database_capacity'],
                           max((row['database'] + 1 for row in state.get('retired', [])), default=0))
            disabled = copy.deepcopy(state)
            for row in disabled['owners'].values():
                row['enabled'] = False
            write_json(service.CONFIG / 'settings.json', dict(config, installed=False))
            write(service.CONFIG / 'environment', service.environment(config, capacity))
            write(service.CONFIG / 'users.acl', service.acl_text(disabled, config), 0o640, gid)
            integration_files(source)
            service.command('systemctl', 'daemon-reload')
            # systemd may garbage-collect a disabled inactive unit. In that
            # case reset-failed reports "not loaded"; start still loads it.
            subprocess.run(['systemctl', 'reset-failed', 'dragonfly'], capture_output=True, timeout=None)
            service.command('systemctl', 'start', 'dragonfly'); service.wait_healthy(config)
            with service.admin(config) as connection:
                # Restore is explicitly a cold-cache operation for this one
                # addon-managed service, including stale persisted databases.
                connection.command('FLUSHALL', 'SYNC')
            from snapshots import durable_save
            durable_save(config, service.STORE)
            service.apply(state, disabled, config)
            write_json(service.STORE / 'desired.json', state)
            write_json(service.STORE / 'applied.json', state)
            write_json(service.CONFIG / 'settings.json', config)
            service.command('systemctl', 'enable', 'dragonfly')
        except Exception:
            service.command('systemctl', 'stop', 'dragonfly')
            for path, data in before.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    write(path, data, 0o640 if path.name == 'users.acl' else
                          0o644 if path in (DROPIN, CRON) else 0o600,
                          gid if path.name == 'users.acl' else 0)
            service.command('systemctl', 'daemon-reload')
            if installed:
                subprocess.run(['systemctl', 'reset-failed', 'dragonfly'], capture_output=True, timeout=None)
                service.command('systemctl', 'start', 'dragonfly'); service.wait_healthy(old_config)
            else:
                for path in (ROUTE, service.CONFIG):
                    if path.exists():
                        shutil.rmtree(path)
                # Retain only the held registry lock until its context exits.
                for path in service.STORE.iterdir():
                    if path.name != 'registry.lock' and path.is_file():
                        path.unlink()
            deployment.rollback() if installed else deployment.remove()
            transaction.finish(service.STORE,filename='restore.json')
            raise RuntimeError('Restore failed; previous configuration was restored, cache may be empty' if installed
                               else 'Restore failed; service remains stopped and recovery backup is retained') from None
    transaction.finish(service.STORE,filename='restore.json')
    deployment.commit()
    return {'ok': True, 'operation': 'restore', 'accounts': len(state['owners']), 'cache_data_restored': False}


def uninstall(value):
    root_only()
    check_integration()
    result = backup(value)
    # Leave the native package and all original files intact, but never start an
    # unmanaged default configuration implicitly after removing authentication.
    service.command('systemctl', 'disable', '--now', 'dragonfly')
    for path in (CRON, DROPIN, BRIDGE):
        path.unlink(missing_ok=True)
    service.command('systemctl', 'daemon-reload')
    for path in (ROUTE, service.CONFIG, service.STORE):
        if path.exists():
            if path.resolve() != path or path.is_symlink():
                raise ValueError('Unexpected removal target')
            shutil.rmtree(path)
    deployment.remove()
    return dict(result, operation='uninstall', native_package_retained=True, native_service_stopped=True)
