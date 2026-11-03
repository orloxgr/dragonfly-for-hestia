# Dragonfly for Hestia

One shared Dragonfly service, separate credentials for each Hestia user and a
separate cache prefix for each site. Version **0.7.1** · GPL-3.0-or-later.

## Quick start

Requires **Ubuntu 26.04 amd64 with Hestia 1.10.5 already installed**.
Run commands over SSH as an administrator. The installer also installs Dragonfly
**2.0.2**; do not install the service separately.

1. **Get the code. Choose one command:**

   For a **new installation**, clone the repository:

   ```sh
   sudo git clone https://github.com/orloxgr/dragonfly-for-hestia.git /usr/local/src/dragonfly-for-hestia
   ```

   To **update an existing checkout**, pull instead:

   ```sh
   sudo git -C /usr/local/src/dragonfly-for-hestia pull --ff-only
   ```

   Wait for Git to finish successfully before continuing.

2. **Install or apply the update.**

   For a **new installation** with a 2 GiB cache budget:

   ```sh
   sudo python3 /usr/local/src/dragonfly-for-hestia/tools/install.py --memory-mb 2048
   ```

   For an **update**, retain the existing memory budget:

   ```sh
   sudo python3 /usr/local/src/dragonfly-for-hestia/tools/install.py
   ```

   Pulling the code alone does not apply the update; run the installer too.

3. **Check that Dragonfly is running.** The output should be `active`.

   ```sh
   sudo systemctl is-active dragonfly
   ```

4. **Log into Hestia as the site owner. Click Plugins → Dragonfly in the top bar.**

   Click **Show connection details**, choose the website and copy the displayed
   credentials, database and cache prefix into your application's object-cache settings.
   Administrators see all accounts and websites, with
   bulk enable/disable controls and links to manage each account.

Done. Existing users and sites are added during installation; new ones are picked
up automatically within a minute. Each owner can change their cache password,
clear a site's cache, or disable access for a site or their whole account.
Application settings are managed separately.

The **2 GiB budget is shared by all users**, not allocated per user. It is a cache
limit, not a reservation or a cap on total process RAM. Hestia's existing code and
templates are not replaced.

To change it later, open **Plugins → Dragonfly** as administrator. Under
**Shared cache memory**, enter the limit in MiB, then click **Apply size and
restart Dragonfly**. For example, `2048` is 2 GiB. This restarts the shared
service for all accounts; credentials, database assignments and prefixes stay
the same. An unchanged value does not restart the service.

While this repository is private, cloning requires your GitHub username and a
token with repository access at the password prompt, not your GitHub password.

## Update

Run these commands separately. First, download the latest code:

```sh
sudo git -C /usr/local/src/dragonfly-for-hestia pull --ff-only
```

After Git finishes successfully, apply the update:

```sh
sudo python3 /usr/local/src/dragonfly-for-hestia/tools/install.py
```

Updates retain existing passwords, site settings and memory budget.
Refresh Hestia with **Ctrl+F5** after updating to load the new menu script.

For changing RAM, backup, restore, removal or importing an existing Dragonfly,
see the [administration reference](docs/administration.md).

See the 0.7.0 [changelog](CHANGELOG.md) for completion, native controls and compatibility changes. Existing service budgets and credentials are preserved on update.

Version 0.7.1 waits through native snapshot loading during resize/recovery, explicitly writes zero for automatic threads, and reports controlled recovery errors in the administrator panel. Updating also completes any pending resize recovery through the existing installer.
