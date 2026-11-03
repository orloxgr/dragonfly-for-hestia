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
    if type(value) is not int or not value > 0:
        raise ValueError('Cache size must be a positive number of MiB')
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


def resize(value, threads=None):
    validate(value)
    # The panel bridge and installer already hold the addon operation lock.
    service.recover_pending()
    config = service.effective_config()
    chosen_threads = config.get('threads', 0) if threads is None else threads
    if type(chosen_threads) is not int or chosen_threads < 0:
        raise ValueError('Threads must be zero for native automatic selection or a positive integer')
    budget = value * MIB
    if config['maxmemory'] == budget and config.get('threads', 0) == chosen_threads:
        return config, False
    for path in paths():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('The managed Dragonfly settings must be root-owned regular files')
    environment = (service.CONFIG / 'environment').read_text()
    old = re.findall(r'^DFLY_maxmemory=(\d+)$', environment, re.M)
    if old != [str(config['maxmemory'])]:
        raise ValueError('The native startup memory limit differs from the saved configuration')
    updated = dict(config, maxmemory=budget, threads=chosen_threads)
    candidate = re.sub(r'^DFLY_maxmemory=\d+$', 'DFLY_maxmemory=' + str(budget), environment, flags=re.M)
    candidate = re.sub(r'^DFLY_proactor_threads=\d+\n?', '', candidate, flags=re.M)
    if chosen_threads:
        # Keep every unrelated native environment choice byte-for-byte.
        candidate = candidate.replace('DFLY_port=' + str(config['port']) + '\n',
            'DFLY_port=' + str(config['port']) + '\nDFLY_proactor_threads=' + str(chosen_threads) + '\n', 1)
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
