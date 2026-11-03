# Changelog

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
