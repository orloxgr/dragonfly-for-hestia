# Changelog

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
