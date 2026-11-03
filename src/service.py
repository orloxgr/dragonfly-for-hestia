"""Manage one native Dragonfly service and its per-account ACL entries."""
import grp
import hashlib
import datetime
import json
from pathlib import Path
import re
import secrets
import subprocess
import time

from files import write, write_json
import transaction
from inventory import collect
from registry import desired_state, locked_store
from resp import Client, RedisError, text

STORE = Path('/var/lib/dragonfly-for-hestia')
CONFIG = Path('/etc/dragonfly-for-hestia')
COMMANDS = ('ping echo get set setex psetex mget mset del unlink exists expire pexpire '
            'ttl pttl scan info watch unwatch multi exec discard incr incrby decr '
            'decrby select type strlen').split()


class ApplyRolledBack(RuntimeError):
    pass


def settings():
    from cache_size import recover
    recover()
    return json.loads((CONFIG/'settings.json').read_text())


def admin(config):
    return Client(config['admin_password'], port=config['port'])


def allowed(owner, config):
    return (owner['enabled'] and not owner['suspended'] and
            owner['package'] not in config.get('denied_packages', []) and
            (config.get('allowed_packages') is None or owner['package'] in config['allowed_packages']))


def prefixes(owner, config):
    if not allowed(owner, config):
        return []
    return [site['prefix'] for site in owner['sites'].values()
            if site['enabled'] and not site['suspended']]


def validate(state, config):
    users, databases = set(), set()
    keep = config.get('retirement_snapshot_keep', 2)
    if not isinstance(keep, int) or not 1 <= keep <= 20:
        raise ValueError('retirement_snapshot_keep must be between 1 and 20')
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', config['admin_password']):
        raise ValueError('Unsupported administrator credential format')
    for owner in state['owners'].values():
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', owner['username']) or owner['username'] == 'default':
            raise ValueError('Invalid tenant ACL identity')
        if owner['username'] in users or owner['database'] in databases:
            raise ValueError('Duplicate tenant assignment')
        users.add(owner['username']); databases.add(owner['database'])
        if not isinstance(owner['database'], int) or not 0 <= owner['database'] < 65536:
            raise ValueError('Invalid tenant database')
        if not isinstance(owner['password'], str) or not 12 <= len(owner['password']) <= 256:
            raise ValueError('Password must be between 12 and 256 characters')
        values = [site['prefix'] for site in owner['sites'].values()]
        for value in values:
            if not re.fullmatch(r'[a-zA-Z0-9_:/.-]{1,200}:', value):
                raise ValueError('Unsafe key prefix')
            if any(other != value and other.startswith(value) for other in values) or values.count(value) != 1:
                raise ValueError('Overlapping site key prefixes')


def acl_words(owner, config, hashed=False):
    permitted = prefixes(owner, config)
    password = ('#'+hashlib.sha256(owner['password'].encode()).hexdigest() if hashed
                else '>'+owner['password'])
    return [('on' if permitted else 'off'), 'resetpass', password, '$'+str(owner['database']),
            'resetkeys', *('~'+p+'*' for p in permitted), 'resetchannels', '-@all',
            *('+'+cmd for cmd in COMMANDS if permitted)]


def acl_text(state, config):
    default = 'USER default on #'+hashlib.sha256(config['admin_password'].encode()).hexdigest()+' ~* &* +@all $all'
    return '\n'.join([default, *('USER '+row['username']+' '+' '.join(acl_words(row,config,True))
                                   for _,row in sorted(state['owners'].items()))])+'\n'


def environment(config, capacity):
    return '\n'.join(['DFLY_bind=127.0.0.1', 'DFLY_port='+str(config['port']),
                      'DFLY_proactor_threads='+str(config['threads']),
                      'DFLY_maxmemory='+str(config['maxmemory']), 'DFLY_cache_mode=true',
                      'DFLY_dbnum='+str(capacity), 'DFLY_requirepass='+config['admin_password'],
                      'DFLY_aclfile='+str(CONFIG/'users.acl')])+'\n'


def wait_healthy(config):
    deadline = time.monotonic()+25
    while True:
        try:
            with admin(config) as connection:
                if connection.command('PING') == 'PONG':
                    return
        except (OSError, RedisError, ConnectionError):
            if time.monotonic() > deadline:
                raise RuntimeError('Dragonfly did not become healthy') from None
            time.sleep(.25)


def command(*args):
    result = subprocess.run(args,capture_output=True,timeout=60)
    if result.returncode:
        raise RuntimeError('Native service operation failed')


def effective_config():
    if (STORE/'restore.json').exists():
        raise ValueError('Finish the pending restore with the README restore command')
    if (STORE/'install.json').exists():
        raise ValueError('Finish the pending installation with the README install command')
    config = settings()
    if not config.get('installed'):
        raise ValueError('The service addon has not been installed')
    return config


def apply(state, previous, config):
    """Apply only changed ACLs. Ordinary updates do not restart the server."""
    validate(state,config)
    gid = grp.getgrnam('dfly').gr_gid
    acl = CONFIG/'users.acl'; env = CONFIG/'environment'
    before_acl, before_env = acl.read_bytes(), env.read_bytes()
    capacity = max(config.get('minimum_databases',256), state['required_database_capacity'])
    capacity = max(capacity, int(re.search(r'^DFLY_dbnum=(\d+)$',before_env.decode(),re.M)[1]))
    candidate_env = environment(config,capacity).encode()
    next_acl = acl_text(state,config).encode()
    old_rows = {row['username']:row for row in (previous or {}).get('owners',{}).values()}
    new_rows = {row['username']:row for row in state['owners'].values()}
    fingerprint = hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    policy_changed = (previous or {}).get('_config_fingerprint') != fingerprint
    needs_restart = before_env != candidate_env
    touched = set()
    try:
        if needs_restart:
            # Capacity expansion is rare. Startup reads the complete candidate ACL.
            write(acl,next_acl,0o640,gid);write(env,candidate_env)
            command('systemctl','restart','dragonfly');wait_healthy(config)
        else:
            with admin(config) as connection:
                live = {text(s) for s in connection.command('ACL','USERS')}
                for username,row in new_rows.items():
                    old = old_rows.get(username)
                    if policy_changed or old is None or acl_words(old,config) != acl_words(row,config) or username not in live:
                        touched.add(username)
                        # Revoking one identity also evicts its existing sessions.
                        # No ACL LOAD: it would disconnect every unrelated tenant.
                        if old and (old['password'] != row['password'] or not prefixes(row,config)):
                            connection.command('ACL','DELUSER',username)
                            live.discard(username)
                        words = acl_words(row,config)
                        # Dragonfly 2.0.2 evicts existing sessions whenever
                        # resetchannels is present. Existing addon identities
                        # already have no channels; retain that restriction and
                        # stream ordinary key-rule changes without disconnects.
                        if username in live:
                            words.remove('resetchannels')
                        connection.command('ACL','SETUSER',username,*words)
                for username in set(old_rows)-set(new_rows):
                    touched.add(username);connection.command('ACL','DELUSER',username)
            if before_acl != next_acl:
                write(acl,next_acl,0o640,gid)
        with admin(config) as connection:
            connection.command('SELECT',capacity-1)
            for row in state['owners'].values():
                if prefixes(row,config):
                    with Client(row['password'],row['username'],config['port']) as tenant:
                        if tenant.command('PING') != 'PONG':
                            raise RuntimeError('Tenant health check failed')
    except Exception:
        write(acl,before_acl,0o640,gid);write(env,before_env)
        if needs_restart:
            command('systemctl','restart','dragonfly');wait_healthy(config)
        else:
            with admin(config) as connection:
                for username in touched:
                    if username in old_rows:
                        connection.command('ACL','SETUSER',username,*acl_words(old_rows[username],config))
                    else:
                        connection.command('ACL','DELUSER',username)
        raise ApplyRolledBack('Apply failed; previous service settings were restored') from None
    state['_config_fingerprint'] = fingerprint
    return {'acl_updates':len(touched),'service_restarted':needs_restart,'database_capacity':capacity}


def transaction_paths():
    return [CONFIG/'users.acl', CONFIG/'environment', STORE/'desired.json', STORE/'applied.json']


def recover_pending():
    record = transaction.read(STORE, transaction_paths())
    if record is None:
        return False
    transaction.restore_files(record)
    # A killed process may have changed a live ACL before writing its startup
    # file. Restart from the durable pre-operation ACL, revoking partial updates.
    command('systemctl', 'restart', 'dragonfly')
    wait_healthy(settings())
    transaction.finish(STORE)
    return True


def reconcile(hestia, mutation=None):
    recover_pending()
    config = effective_config()
    inventory = collect(hestia)
    with locked_store(STORE) as desired_path:
        old = json.loads(desired_path.read_text()) if desired_path.exists() else None
        state = desired_state(old,inventory,'dragonfly')
        if mutation:
            mutation(state,config)
        applied_path = STORE/'applied.json'
        previous = json.loads(applied_path.read_text()) if applied_path.exists() else None
        validate(state, config)
        transaction.begin(STORE, transaction_paths())
        try:
            result = apply(state,previous,config)
            result.update(cleanup_retired(state,config))
            if old != state:
                write_json(desired_path,state)
            if previous != state:
                write_json(applied_path,state)
        except ApplyRolledBack:
            transaction.finish(STORE)
            raise
        except Exception:
            recover_pending()
            raise
        transaction.finish(STORE)
        write_json(STORE/'last-run.json',{'ok':True,
                   'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**result})
        return state,config,result


def flush_site(owner, site, config):
    removed = 0
    # Native ACLs enforce the account DB; the root bridge additionally narrows
    # cleanup to this site's literal prefix. Never FLUSHALL/FLUSHDB for tenants.
    with admin(config) as connection:
        connection.command('SELECT',owner['database'])
        cursor = 0
        while True:
            cursor,keys = connection.command('SCAN',cursor,'MATCH',site['prefix']+'*','COUNT',500)
            for start in range(0,len(keys),100):
                removed += connection.command('UNLINK',*keys[start:start+100])
            if int(cursor) == 0:
                return removed


def cleanup_retired(state,config):
    """Release a retired DB only after native revocation and verified removal."""
    pending,removed = 0,0
    cleaned_databases = []
    active_databases = {row['database'] for row in state['owners'].values()}
    for retired_owner,owner in [*((False,row) for row in state['owners'].values()),
                                 *((True,row) for row in state['retired'])]:
        if retired_owner and owner.get('cleaned'):
            continue
        sites = [*owner.get('retired_sites',[])]
        if retired_owner:
            sites += list(owner['sites'].values())
        try:
            if retired_owner:
                if owner['database'] in active_databases:
                    raise ValueError('Retired database is still assigned')
                with admin(config) as connection:
                    connection.command('ACL','DELUSER',owner['username'])
            for site in sites:
                if site.get('cleaned'):
                    continue
                if not re.fullmatch(r'[a-zA-Z0-9_:/.-]{1,200}:',site['prefix']):
                    raise ValueError('Unsafe retired key prefix')
                removed += flush_site(owner,site,config)
                site['cleaned'] = True
            if retired_owner:
                with admin(config) as connection:
                    connection.command('SELECT',owner['database'])
                    if connection.command('DBSIZE') == 0:
                        cleaned_databases.append(owner)
                    else:
                        pending += 1
        except (ValueError,RedisError,OSError,ConnectionError):
            # Keep the slot reserved and retry later. Cleanup failure does not
            # roll back a successful revocation or disturb unrelated tenants.
            pending += 1
    if cleaned_databases:
        try:
            # A stale persisted snapshot must not repopulate a reassigned DB.
            # Make retirement durable before acknowledging any reusable slots.
            from snapshots import durable_save
            durable_save(config, STORE)
            for owner in cleaned_databases:
                owner['cleaned'] = True
        except (RedisError,OSError,ConnectionError):
            pending += len(cleaned_databases)
    return {'cleanup_pending':pending,'retired_keys_removed':removed}


def request(hestia, owner_name, action, payload):
    domain = payload.get('domain')
    def mutate(state,config):
        owner = state['owners'][owner_name]
        if domain is not None and domain not in owner['sites']:
            raise ValueError('Domain is not owned by this account')
        if action == 'password':
            password = payload.get('password')
            if not isinstance(password,str) or not 12 <= len(password) <= 256:
                raise ValueError('Password must be between 12 and 256 characters')
            owner['password'] = password
        elif action == 'toggle-account':
            if not isinstance(payload.get('enabled'),bool):
                raise ValueError('Expected an enable/disable choice')
            owner['enabled'] = payload['enabled']
        elif action == 'toggle-site':
            if domain not in owner['sites'] or not isinstance(payload.get('enabled'),bool):
                raise ValueError('Invalid site choice')
            owner['sites'][domain]['enabled'] = payload['enabled']
    if action not in ['status','credentials','password','toggle-account','toggle-site','test','flush']:
        raise ValueError('Unsupported service action')
    state,config,result = reconcile(hestia,mutate)
    owner = state['owners'][owner_name]
    if domain is not None and domain not in owner['sites']:
        raise ValueError('Domain is not owned by this account')
    response = {'ok':True,'owner':owner_name,'enabled':owner['enabled'],
                'allowed':owner['package'] not in config.get('denied_packages',[]) and
                          (config.get('allowed_packages') is None or owner['package'] in config['allowed_packages']),
                'sites':[{'domain':name,'aliases':row['aliases'],'enabled':row['enabled'],
                          'suspended':row['suspended'],'prefix':row['prefix']}
                         for name,row in sorted(owner['sites'].items())]}
    if action == 'credentials':
        response['connection'] = {'host':'127.0.0.1','port':config['port'],
                                  'username':owner['username'],'password':owner['password'],
                                  'database':owner['database']}
    if action == 'flush':
        if domain is None:
            raise ValueError('Select a site to clear')
        response['removed_keys'] = flush_site(owner,owner['sites'][domain],config)
    if action == 'test':
        if domain is None or not allowed(owner,config) or not owner['sites'][domain]['enabled']:
            raise ValueError('Select an enabled site')
        with Client(owner['password'],owner['username'],config['port']) as connection:
            probe = owner['sites'][domain]['prefix']+'connection-test:'+secrets.token_hex(16)
            try:
                connection.command('SET',probe,'ok','EX',10)
                response['connection_ok'] = connection.command('GET',probe) == b'ok'
            finally:
                connection.command('DEL',probe)
    return response
