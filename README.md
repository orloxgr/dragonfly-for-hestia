# Dragonfly for Hestia

One shared Dragonfly service, separate credentials for each Hestia user and a
separate cache prefix for each site. Version **0.4.2** Ξ’Β· GPL-3.0-or-later.

## Quick start

Requires **Ubuntu 26.04 amd64 with Hestia 1.10.5 already installed**.
Run commands over SSH as an administrator. The installer also installs Dragonfly
**2.0.2**; do not install the service separately.

1. **Clone.**

   ```sh
   sudo git clone https://github.com/orloxgr/dragonfly-for-hestia.git /usr/local/src/dragonfly-for-hestia
   ```

2. **Install with a 2 GiB cache budget.**

   ```sh
   sudo python3 /usr/local/src/dragonfly-for-hestia/tools/install.py --memory-mb 2048
   ```

3. **Check that Dragonfly is running.** The output should be `active`.

   ```sh
   sudo systemctl is-active dragonfly
   ```

4. **Log into Hestia as the site owner and open:**

   ```text
   https://YOUR-SERVER:8083/plugins/dragonfly/
   ```

   Click **Open Dragonfly for Hestia**, then copy the connection details and
   site's prefix into your application's object-cache settings. An administrator
   can use Hestia's **Log in as** action to open the owner's account.

Done. Existing users and sites are added during installation; new ones are picked
up automatically within a minute. Each owner can change their cache password,
clear a site's cache, or disable access for a site or their whole account.
Application settings are managed separately.

The **2 GiB budget is shared by all users**, not allocated per user. It is a cache
limit, not a reservation or a cap on total process RAM. Hestia's existing code and
templates are not replaced.

While this repository is private, cloning requires your GitHub username and a
token with repository access at the password prompt, not your GitHub password.

## Update

```sh
sudo git -C /usr/local/src/dragonfly-for-hestia pull --ff-only
sudo python3 /usr/local/src/dragonfly-for-hestia/tools/install.py
```

Updates retain existing passwords, site settings and memory budget.

For changing RAM, backup, restore, removal or importing an existing Dragonfly,
see the [administration reference](docs/administration.md).
