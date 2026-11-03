# Administration reference

An independent Hestia addon for one shared Dragonfly service, with personal
credentials, native database isolation and a separate prefix for every website.
Existing Hestia code and templates are not replaced.

Version **0.7.1**.

Source repository: [orloxgr/dragonfly-for-hestia](https://github.com/orloxgr/dragonfly-for-hestia).

For the four-step installation, see [Quick start](../README.md#quick-start).

## Installation details

Initial verified platform: **Ubuntu 26.04 amd64, Hestia 1.10.5, Dragonfly 2.0.2**.
Install Hestia first, then clone the repository into the retained source checkout:

```sh
sudo git clone https://github.com/orloxgr/dragonfly-for-hestia.git /usr/local/src/dragonfly-for-hestia
cd /usr/local/src/dragonfly-for-hestia
sudo python3 tools/install.py --memory-mb 2048
```

Keep `/usr/local/src/dragonfly-for-hestia` for future updates and recovery.

When Dragonfly is absent, the installer downloads the official pinned `.deb`,
verifies its SHA256 and installs it with APT. Authentication and loopback binding
are configured before package auto-start. It refuses a conflicting listener or an
unmanaged existing installation. The initial service starts with authentication and loopback-only access.

If package installation or first startup is interrupted, run the same command
again. The private installation journal retains the first generated credentials,
including when the native package has already been installed; no adoption manifest
or manual cleanup is needed for that retry.

To update the retained checkout and installed addon:

```sh
sudo git -C /usr/local/src/dragonfly-for-hestia pull --ff-only
sudo python3 /usr/local/src/dragonfly-for-hestia/tools/install.py
```

Rerunning the installer updates addon files and reconciles existing accounts.
Reinstallation preserves credentials and assignments. It does not automatically
change to an unverified Dragonfly release.
The memory argument sets the initial **server-wide** cache budget, shared by all
hosting accounts; it is not a per-user allowance. Existing budgets are preserved
when rerunning the installer.

To change the shared cache budget later, open **Plugins → Dragonfly** as an
administrator. Enter the size in MiB under **Shared cache memory**, then click
**Apply size and restart Dragonfly**. `2048` sets a 2 GiB cache budget.
The panel updates both durable settings and native startup configuration and
verifies the running limit with `CONFIG GET maxmemory`. Existing credentials,
database assignments and site prefixes are preserved. A failed or interrupted
change restores the previous settings through the private resize journal.
An unchanged value does not restart the service. A changed value restarts the
shared native service, so active connections briefly disconnect and the cache
may need to warm again. Process memory also includes runtime overhead outside
the cache budget. Ordinary accounts cannot change this server-wide setting.

## Open the interface

After logging into Hestia, open:

```text
https://YOUR-SERVER:8083/plugins/dragonfly/
```

A direct bookmark first shows an **Open Dragonfly for Hestia** link; following it
retains Hestia's normal same-origin/session checks. Existing menu files are not
modified. Administrators see all accounts and websites on the addon home page.
Select accounts or websites for bulk enable/disable, or choose **All accounts /
websites**. Account selections include all their websites. **Manage account** and
**Manage website** open the owner controls directly. Website changes retain the
separate account enable/disable choice. Native suspension and package restrictions
continue to apply. Hestia's **Log in as** still opens the selected owner's view.

**Show connection details** displays the website selector, its cache prefix, host,
port, username, password and database together. Changing the website immediately
updates the displayed prefix. Each website also has a direct connection-details button.

The owner can view personal connection details and each site's prefix, change the
Dragonfly password, test a site's actual connection, clear only its cache entries,
and disable/enable individual sites or the entire account.

One owner's sites share that owner's credentials/database and have distinct
prefixes. Different owners are bound to different databases by the server, with
restricted commands and key patterns. Owners never receive the global admin
credential.

Applications are independent of this addon. It does not inspect installed
WordPress/UltraCache plugins or edit application files, settings or credentials.
Changing a Dragonfly password or disabling service access changes only the
service; the application operator configures its connection separately. Handling
an unavailable backend or invalid credentials belongs to the application.

## Automatic account lifecycle

The addon reads native Hestia users, packages, domains, aliases and suspension.
An addon-owned root cron entry reconciles once per minute; opening the owner
interface also reconciles immediately. No persistent management daemon is added.

Credentials and site scopes survive rebuilds, alias/package changes, restarts and
ordinary Hestia password changes. Replacement accounts receive fresh identities.
Suspended/deleted owners lose their ACL identity or access. Retired entries are
removed before a database slot can be reused. If cleanup fails, the slot stays
reserved and reconciliation retries. Ordinary ACL changes update affected
accounts without restarting the server; password changes evict that account's
old sessions.
Database retirement is acknowledged only after a native snapshot completes, so
an older persisted snapshot cannot repopulate a reassigned database on restart.
The addon retains two snapshot sets created by its retirement/restore operations
(`retirement_snapshot_keep`, any positive count). It tracks only files
created or replaced by those operations; existing untracked snapshots and native
shutdown/scheduled snapshots are retained. The initial retention implementation
supports local native DFS snapshots with the default `dump-{timestamp}` naming.

For immediate administrator reconciliation:

```sh
sudo /usr/local/hestia/bin/v-dragonfly-hestia reconcile
```

The JSON summary reports ACL updates, restart, capacity and pending cleanup.
Private state is under `/var/lib/dragonfly-for-hestia/`; configuration is under
`/etc/dragonfly-for-hestia/`. The cron file, panel route, command and native
service drop-in are addon-owned. Complete installed code generations live in
`/opt/dragonfly-for-hestia.releases/`; `/opt/dragonfly-for-hestia` points atomically
to the active generation. A failed normal upgrade restores the previous pointer.
Interrupted publication leaves a complete generation and the same installer can
finish the update. The packaged unit and original environment/ACL
files are retained.

Administrators can set `allowed_packages` (null means all packages) and
`denied_packages` in private `settings.json`, then reconcile. User choices cannot
override a package restriction. Package policy is administered through this root-only configuration.

## Adopt an existing Dragonfly

Existing installations require an explicit complete root-owned mode-600 manifest.
The installer authenticates to the existing service, accounts for its ACL users
and refuses unknown occupied database scopes. Example structure:

```json
{
  "schema": 1,
  "port": 6379,
  "admin_password": "EXISTING_ADMIN_PASSWORD",
  "owners": {
    "alice": {
      "username": "alice",
      "password": "EXISTING_PERSONAL_PASSWORD",
      "database": 0,
      "sites": {"example.com": "existing:site:prefix:"}
    }
  }
}
```

List all sites of each imported owner and every existing non-default ACL user.
Keep the manifest outside public directories, then run:

```sh
sudo chmod 600 /root/dragonfly-adoption.json
sudo python3 /usr/local/src/dragonfly-for-hestia/tools/install.py --adopt /root/dragonfly-adoption.json --memory-mb 2048
```

Imported site passwords, usernames, database numbers and prefixes are retained.

## Back up, restore or remove

Use the retained checkout at `/usr/local/src/dragonfly-for-hestia` from a root shell or with sudo:

```sh
sudo install -d -m 700 /root/dragonfly-backups
sudo python3 /usr/local/src/dragonfly-for-hestia/tools/manage.py backup /root/dragonfly-backups/config-2026-10-31.json
sudo python3 /usr/local/src/dragonfly-for-hestia/tools/manage.py restore /root/dragonfly-backups/config-2026-10-31.json
```

The private JSON archive includes addon settings, global and personal credentials,
site prefixes, choices and assignments, with a checksum for accidental damage.
It contains no cache data or application files. Keep the directory root-owned
mode 700 and archive mode 600; the command refuses public paths and overwriting
an existing backup. These maintenance commands require an administrator shell.

Restore briefly stops this one Dragonfly service and clears its cache data before
activating the restored assignments, preventing stale entries from crossing a
restored account boundary. Existing sessions disconnect. Current Hestia inventory
remains authoritative: archived users present in Hestia keep their credentials
and are explicitly rebound by username, absent users are retired, and new Hestia
users receive new assignments. Restore Hestia accounts first when recovering a
server. Keep a separate addon archive with the native Hestia account backups;
Hestia account archives alone do not include this shared cache registry. Applications are never modified. A failed activation restores the prior
configuration, with the cache potentially empty. If a restore process is killed,
repeat that same restore command: the private undo record recovers the previous
configuration before retrying. Owner actions wait until the root restore finishes.

Interrupted owner/lifecycle configuration changes recover the last committed
configuration on the next reconciliation. This rare recovery can restart the
shared native service; ordinary no-op runs and credential changes retain its
process.

To remove the addon, provide a new private backup filename:

```sh
sudo python3 /usr/local/src/dragonfly-for-hestia/tools/manage.py uninstall /root/dragonfly-backups/before-removal.json
```

Removal creates the recovery archive, stops/disables the native Dragonfly service
and removes only this addon's route, command, cron entry, drop-in, code, config
and state. It retains the native package, original native configuration and
native snapshot files. Other Hestia services/templates remain untouched. Restore
using `tools/manage.py restore` from your retained checkout to reinstall the addon
and recover its credentials. On a replacement server, install Hestia and the
supported service/addon first, then restore the archive.

## Compatibility and operating limits

The service listens on loopback; remote clients use an appropriate tunnel.
The shared process shares CPU, memory and availability, without per-account RAM
quotas. Initial capacity covers at least 256 database assignments and grows when
needed; native capacity growth requires a controlled service restart. Supported
filesystems must provide account-directory creation timestamps. Supported versions: Ubuntu 26.04 amd64 / Hestia 1.10.5 / Dragonfly 2.0.2.
Unknown installation platform or service versions are refused. The installer pins
the verified upstream binary and does not promise compatibility with an unknown
future major release; updating the addon uses the install command from its new
checkout. The addon does not change firewall, SSH or login
authentication settings.

## Development checks

The Linux state-model suite is independent of a running service:

```sh
python3 tests/test_registry.py
```

The suite checks account/domain lifecycle, identity persistence, configuration
isolation and concurrent registry writers without creating hosting accounts.

## License and upstream

GPL-3.0-or-later; see `LICENSE`.

- [Dragonfly 2.0.2](https://github.com/dragonflydb/dragonfly/releases/tag/v2.0.2)
- [Dragonfly ACL](https://www.dragonflydb.io/docs/managing-dragonfly/acl)
- [Hestia customisation](https://hestiacp.com/docs/server-administration/customisation)

## Panel menu

Hestia automatically includes the addon-owned `dragonfly-for-hestia.js` script from
`/usr/local/hestia/web/js/custom_scripts/`. Installed addons share one **Plugins**
dropdown; each installer and uninstaller manages only its own script. Native
Hestia login, account context and permission checks continue to apply. If the
header layout is unfamiliar, the script leaves the page alone; the direct
`/plugins/dragonfly/` URL remains available.

See [Hestia’s custom-script extension point](https://github.com/hestiacp/hestiacp/blob/1.10.5/web/js/custom_scripts/README.txt).

## Native controls and completion (0.7.0)

**Shared cache memory** accepts a positive MiB value, subject to actual native
startup validity and rollback. **Worker threads** accepts `0` for native automatic
selection or a positive count. Existing values survive addon updates; changing
these controls restarts the shared service and verifies the resulting memory
budget. Zero does not silently replace an existing explicit value on upgrade.

Tenant ACLs permit native read/write/transaction data operations plus tested
EVAL/EVALSHA and DUMP/RESTORE. Database and key-prefix enforcement applies to
script commands too. Global administration, global flushes and unrestricted
SCRIPT management remain unavailable. This expands application compatibility
without granting a tenant control of the shared service.

There are no addon request/file/RESP/output byte quotas or separate administrative
work deadlines. Both bridge streams are drained completely. Authentication,
private-file ownership, scope validation, service-failure checks and journalled
rollback remain in place. Real native errors are not reported as success.
Initial installation accepts `--port` with a valid loopback TCP port; restore
checks native compatibility rather than an exact service-version string. The
fresh-install package still has its pinned official URL and verified checksum.

On the tested Dragonfly 2.0.2, per-subcommand SCRIPT ACL grants are unavailable. SCRIPT remains denied because granting the whole command would also permit shared SCRIPT FLUSH/KILL operations. Applications can use EVAL/EVALSHA with the verified DB/key restrictions.

### Startup readiness and resize recovery (0.7.1)

A native listener may accept connections while a snapshot is still loading. LOADING, BUSY and TRYAGAIN responses are readiness states: the addon waits for authenticated PONG and verifies the memory budget. Actual credential errors and stopped/failed services still fail. Zero threads is written explicitly in the environment, so inherited defaults cannot replace the automatic choice. Failed changes retain journalled recovery, and administrator errors distinguish restored settings from pending recovery without disclosing native replies or credentials.
