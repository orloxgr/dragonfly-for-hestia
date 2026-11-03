"""Persist a shared Dragonfly cache budget with restart and crash recovery."""
import json
import re
import stat

from files import write, write_json
from resp import text
import service
import transaction

JOURNAL = 'resize.json'
MIB = 1024 * 1024


def validate(value):
    if type(value) is not int or not 256 <= value <= 1048576:
        raise ValueError('Cache size must be 256–1048576 MiB')
    return value


def paths():
    return [service.CONFIG / 'settings.json', service.CONFIG / 'environment']


def check_budget(config):
    with service.admin(config) as connection:
        result = connection.command('CONFIG', 'GET', 'maxmemory')
    if (not isinstance(result, list) or len(result) != 2 or text(result[0]) != 'maxmemory'
            or text(result[1]) != str(config['maxmemory'])):
        raise RuntimeError('The running Dragonfly memory limit does not match the requested size')


def start(config):
    service.command('systemctl', 'restart', 'dragonfly')
    service.wait_healthy(config)
    check_budget(config)


def recover():
    record = transaction.read(service.STORE, paths(), filename=JOURNAL)
    if record is None:
        return False
    transaction.restore_files(record)
    config = json.loads((service.CONFIG / 'settings.json').read_text())
    start(config)
    transaction.finish(service.STORE, filename=JOURNAL)
    return True


def resize(value):
    validate(value)
    # The panel bridge and installer already hold the addon operation lock.
    service.recover_pending()
    config = service.effective_config()
    if value < max(1, config['threads']) * 256:
        raise ValueError('Dragonfly needs at least 256 MiB per configured worker thread')
    budget = value * MIB
    if config['maxmemory'] == budget:
        return config, False
    for path in paths():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('The managed Dragonfly settings must be root-owned regular files')
    environment = (service.CONFIG / 'environment').read_text()
    old = re.findall(r'^DFLY_maxmemory=(\d+)$', environment, re.M)
    if old != [str(config['maxmemory'])]:
        raise ValueError('The native startup memory limit differs from the saved configuration')
    updated = dict(config, maxmemory=budget)
    candidate = re.sub(r'^DFLY_maxmemory=\d+$', 'DFLY_maxmemory=' + str(budget), environment, flags=re.M)
    transaction.begin(service.STORE, paths(), filename=JOURNAL)
    try:
        write(service.CONFIG / 'environment', candidate)
        write_json(service.CONFIG / 'settings.json', updated)
        start(updated)
    except Exception:
        try:
            recover()
        except Exception:
            raise RuntimeError('Dragonfly resize failed; recovery is pending. Check the native service.') from None
        raise RuntimeError('Dragonfly resize failed; the previous memory limit was restored.') from None
    transaction.finish(service.STORE, filename=JOURNAL)
    return updated, True
