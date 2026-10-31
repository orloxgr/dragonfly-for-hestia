<?php
require $root . '/web/templates/header.php';
$panel = top_panel($headerOwner, $TAB);
?>
<script>document.title = <?= json_encode($meta['title'], JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?>;</script>
<div class="toolbar"><div class="toolbar-inner"><div class="toolbar-buttons">
    <?php if ($isAdmin): ?><a class="button button-secondary" href="./">All accounts</a><?php endif; ?>
    <a class="button button-secondary" href="/list/web/"><i class="fas fa-arrow-left icon-blue"></i>Back</a>
</div></div></div>
<div class="container"><div class="form-container form-container-wide">
    <h1 class="u-mb10"><?= $escape($meta['title']) ?></h1>
    <p class="u-mb20">Account: <strong><?= $escape($owner) ?></strong></p>
    <?php if ($pageError !== ''): ?>
        <div class="alert alert-danger u-mb20" role="alert"><i class="fas fa-circle-exclamation"></i><p><?= $escape($pageError) ?></p></div>
    <?php elseif ($message !== ''): ?>
        <div class="alert alert-<?= $escape($messageType) ?> u-mb20" role="status"><i class="fas fa-<?= $messageType === 'success' ? 'circle-check' : 'circle-exclamation' ?>"></i><p><?= $escape($message) ?></p></div>
    <?php endif; ?>
    <?php if ($managed): ?>
        <p class="u-mb20"><i class="fas fa-database <?= !empty($data['enabled']) && !empty($data['allowed']) ? 'icon-green' : 'icon-red' ?>"></i>
            Dragonfly: <strong><?= !empty($data['enabled']) && !empty($data['allowed']) ? 'Enabled' : 'Disabled' ?></strong></p>
        <?php if (empty($data['allowed'])): ?><div class="alert alert-info u-mb20" role="status"><p>The hosting package does not currently allow Dragonfly.</p></div><?php endif; ?>
        <div class="toolbar-buttons u-mb20">
            <form method="post"><?php $formFields('credentials'); ?><button type="submit" class="button button-secondary"><i class="fas fa-key icon-orange"></i>Show connection details</button></form>
            <form method="post"><?php $formFields('toggle-account'); ?><input type="hidden" name="enabled" value="<?= empty($data['enabled']) ? '1' : '0' ?>"><button type="submit" class="button button-secondary"><?= empty($data['enabled']) ? 'Enable' : 'Disable' ?> for this account</button></form>
        </div>
        <?php if (isset($data['connection'])): ?>
            <section class="u-mb20" aria-label="Connection details">
                <h2 class="u-mb20">Connection details</h2>
                <?php foreach ($data['connection'] as $key => $value): ?>
                    <div class="u-mb10"><label class="form-label" for="connection-<?= $escape($key) ?>"><?= $escape(ucfirst($key)) ?></label>
                        <input class="form-control" id="connection-<?= $escape($key) ?>" type="text" value="<?= $escape($value) ?>" readonly autocomplete="off"></div>
                <?php endforeach; ?>
            </section>
        <?php endif; ?>
        <details class="box-collapse u-mb20">
            <summary class="box-collapse-header"><i class="fas fa-key u-mr10"></i>Change Dragonfly password</summary>
            <div class="box-collapse-content"><form method="post">
                <?php $formFields('password'); ?>
                <div class="u-mb20"><label class="form-label" for="new-password">New password</label><input class="form-control" type="password" id="new-password" name="password" minlength="12" maxlength="256" required autocomplete="new-password"></div>
                <button class="button" type="submit"><i class="fas fa-floppy-disk icon-purple"></i>Change password</button>
            </form></div>
        </details>
        <h2 class="u-mb20">Websites</h2>
    <?php elseif ($pageError === ''): ?>
        <div class="alert alert-info u-mb20" role="status"><p>Install the Dragonfly service addon to enable cache management.</p></div>
    <?php endif; ?>
    <?php foreach ($data['sites'] as $site): ?>
        <details class="box-collapse u-mb10" <?= $site['domain'] === $selectedDomain ? 'open' : '' ?>>
            <summary class="box-collapse-header"><i class="fas fa-globe u-mr10"></i><?= $escape($site['domain']) ?></summary>
            <div class="box-collapse-content">
                <p class="u-mb10">Status: <strong><?= $site['suspended'] ? 'Suspended' : (!empty($site['enabled']) ? 'Enabled' : 'Disabled') ?></strong></p>
                <?php if ($site['aliases']): ?><p class="u-mb10">Aliases: <?= $escape(implode(', ', $site['aliases'])) ?></p><?php endif; ?>
                <?php if (isset($site['prefix'])): ?>
                    <div class="u-mb20"><label class="form-label" for="prefix-<?= $escape($site['domain']) ?>">Cache prefix</label><input class="form-control" type="text" id="prefix-<?= $escape($site['domain']) ?>" value="<?= $escape($site['prefix']) ?>" readonly></div>
                <?php endif; ?>
                <?php if ($managed): ?>
                    <div class="toolbar-buttons">
                        <form method="post"><?php $formFields('test', $site['domain']); ?><button type="submit" class="button button-secondary"><i class="fas fa-plug icon-blue"></i>Test connection</button></form>
                        <form method="post"><?php $formFields('flush', $site['domain']); ?><button type="submit" class="button button-secondary"><i class="fas fa-trash icon-red"></i>Clear site cache</button></form>
                        <form method="post"><?php $formFields('toggle-site', $site['domain']); ?><input type="hidden" name="enabled" value="<?= empty($site['enabled']) ? '1' : '0' ?>"><button type="submit" class="button button-secondary"><?= empty($site['enabled']) ? 'Enable site' : 'Disable site' ?></button></form>
                    </div>
                <?php endif; ?>
            </div>
        </details>
    <?php endforeach; ?>
    <?php if ($managed && !$data['sites']): ?><p class="u-mb20">This account has no websites.</p><?php endif; ?>
    <p class="u-mt20"><small>Version <?= $escape($meta['version']) ?></small></p>
</div></div>
<?php require $root . '/web/templates/footer.php'; ?>
