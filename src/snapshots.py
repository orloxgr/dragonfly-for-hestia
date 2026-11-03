"""Bound only snapshots created by addon retirement; never prune existing backups."""
import json
from pathlib import Path
import re

from files import write_json
from resp import Client, RedisError, text


def local_files(directory, pattern):
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise ValueError('A local native snapshot directory is required')
    if not re.fullmatch(r'[A-Za-z0-9_.{}-]+', pattern):
        raise ValueError('Unsupported native snapshot filename')
    expression = re.escape(pattern).replace(r'\{timestamp\}', r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d')
    expression += r'-(?:summary|\d{4})\.dfs'
    return {p.name: (p.stat().st_mtime_ns, p.stat().st_size)
            for p in directory.iterdir() if re.fullmatch(expression, p.name)
            and p.is_file() and not p.is_symlink()}


def durable_save(config, store):
    """Caller holds the addon operation/registry lock. SAVE failure never retires a DB."""
    with Client(config['admin_password'], port=config['port'], timeout=None) as connection:
        directory = Path(text(connection.command('CONFIG', 'GET', 'dir')[1]))
        pattern = text(connection.command('CONFIG', 'GET', 'dbfilename')[1])
        before = local_files(directory, pattern)
        if connection.command('SAVE') != 'OK':
            raise RedisError('Snapshot did not complete')
        after = local_files(directory, pattern)
    changed = sorted(name for name, signature in after.items() if before.get(name) != signature)
    ledger_path = Path(store) / 'snapshot-retention.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'schema': 1, 'groups': []}
    groups = ledger['groups']
    # Names can repeat when two SAVE operations occur in the same second.
    groups = [g for g in groups if not (g['directory'] == str(directory) and
                                       set(g['files']).intersection(changed))]
    if changed:
        groups.append({'directory': str(directory), 'files': changed})
    keep = config.get('retirement_snapshot_keep', 2)
    if not isinstance(keep, int) or keep < 1:
        raise ValueError('retirement_snapshot_keep must be positive')
    retained, obsolete = groups[-keep:], groups[:-keep]
    # Record retained groups before unlink. A crash can leave an extra old file,
    # never a ledger entry that deletes a later unrelated filename.
    write_json(ledger_path, {'schema': 1, 'groups': retained})
    for group in obsolete:
        if group['directory'] != str(directory):
            continue
        for name in group['files']:
            if name in after and name not in {n for g in retained for n in g['files']}:
                path = directory / name
                if path.parent != directory or path.is_symlink():
                    raise ValueError('Invalid tracked snapshot path')
                path.unlink(missing_ok=True)
    return len(retained)
