# Changelog

## 0.7.1 · 2026-11-04

- Fix startup health checks treating transient snapshot-loading responses as bad administrator credentials. Retry LOADING/BUSY/TRYAGAIN until authenticated PONG or an actual failure, without an addon work deadline.
- Write `DFLY_proactor_threads=0` explicitly for automatic mode, overriding inherited defaults while preserving unrelated startup settings.
- Preserve safe protocol error codes without exposing raw native replies. Show controlled restored/pending-recovery messages to administrators instead of the generic account-loading error.
- Avoid immediately repeating failed recovery while rendering its error page; keep the undo journal until successful recovery.
- Exercise native restarts with an existing snapshot, 2048 MiB and both explicit/automatic thread modes, validating tenant authentication, stored data, budget and journal completion.

## 0.7.0 · 2026-11-04

- Replace the narrow 29-command tenant allowlist with native data/transaction categories and tested EVAL/EVALSHA and DUMP/RESTORE support. Native DB/key-prefix ACLs remain mandatory; global administration, destructive global flushes and unrestricted SCRIPT management stay denied.
- Add administrator worker-thread control: zero selects native automatic sizing; positive values choose a native worker count. Existing thread and memory choices are preserved during upgrades.
- Remove addon memory-size floors/ceilings, per-thread budget checks, RESP/request/file/output ceilings, snapshot-count ceiling and administrative/download deadlines. Actual native validity and journalled rollback remain authoritative.
- Allow a valid loopback TCP port during initial installation/adoption and native-compatible backup restores without an exact service-version pin. Official fresh-install package checksum verification remains.
- Open the normal panel directly after native session checks, and drain full bridge stdout/stderr concurrently to avoid truncated JSON and pipe deadlocks.

## 0.6.0

- Add an administrator-only shared memory limit in MiB, with hover explanations,
  native restart and verification of the effective Dragonfly limit.
- Preserve credentials, database assignments and site prefixes. Keep a private
  undo record for failed or interrupted size changes; unchanged sizes do not restart.
- Update installation documentation and remove private-clone login instructions.

## 0.5.2

- Show the website selector and its cache prefix together with all connection details.
- Add a direct connection-details action for each website and jump to the selected details.

## 0.5.1

- Fix dropdown links closing before pointer clicks can navigate.
- Preserve internal keyboard focus and navigation when another installed addon still has an older menu script.

## 0.5.0

- Add an administrator dashboard listing all native accounts and websites.
- Add bulk account/site enable and disable, plus direct owner management.

## 0.4.4

- Render addon pages with Hestia’s native header, navigation, selected theme, forms and alerts.
- Keep owner actions in HTML and show visible success or failure feedback.
- Remove the legacy website-access probe from the owner interface.
- Test cache connections with a unique expiring key and clean it up after the read/write check.

## 0.4.3

- Add a Plugins menu in Hestia’s top bar through its native custom-scripts loader.
- Share one dropdown with other installed addons, without editing Hestia templates.
- Install, update, roll back and remove only this addon’s menu script.

## 0.4.2

- Create the shared Hestia plugins directory when installing the first addon.
- Preserve existing plugin-directory permissions and neighboring plugins on installation and retry.

## 0.4.1

- Administrator installation failures show command arguments, exit status, subprocess output and Python tracebacks.
- Panel PHP syntax-check failures retain native compiler diagnostics.

## 0.4.0

Initial release.

- Shared native Dragonfly service with per-owner ACL credentials and database isolation.
- Automatic Hestia account/domain discovery and separate site key prefixes.
- Owner password, connection test, scoped flush and enable/disable controls.
- Package-aware access policy and one-minute lifecycle reconciliation.
- Private configuration archives, cold restore and independent removal.
- Durable installation, live-configuration and restore recovery.
- Atomic installed-code generations and failed-upgrade rollback.
- Application configuration remains independently managed.
