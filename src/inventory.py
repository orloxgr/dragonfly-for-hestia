"""Read the complete native Hestia inventory, or fail without changing state."""
import pwd
from pathlib import Path
import subprocess


def collect(hestia):
    users = hestia('v-list-users', 'json')
    result = {}
    for owner, row in sorted(users.items()):
        # Directory birth time survives password/package changes but differs for
        # replacement accounts, even if name/UID/creation-second are recycled.
        directory = Path('/usr/local/hestia/data/users') / owner
        birth = subprocess.check_output(['stat','--format=%w','--',str(directory)],text=True).strip()
        if not birth or birth == '-':
            raise ValueError('A stable account creation identity is unavailable')
        identity = str(pwd.getpwnam(owner).pw_uid) + ':' + birth
        domains = hestia('v-list-web-domains', owner, 'json')
        result[owner] = {
            'identity':identity, 'package':row['PACKAGE'], 'role':row['ROLE'],
            'suspended':row['SUSPENDED'] == 'yes',
            'sites':{domain:{'aliases':[s.strip() for s in web.get('ALIAS','').split(',') if s.strip()],
                             'suspended':web.get('SUSPENDED') == 'yes'}
                     for domain, web in domains.items()},
        }
    return result
