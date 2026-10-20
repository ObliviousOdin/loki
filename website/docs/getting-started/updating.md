---
sidebar_position: 3
title: "Updating & Uninstalling Loki"
description: "Keep a Loki source preview pinned, review its owned update source, and preserve data when changing installations."
---

# Updating & Uninstalling Loki

## Updating

Choose a release from [Loki releases](https://github.com/ObliviousOdin/loki/releases) and read its exact source, migration and verification notes. The known published [alpha.1 example](https://github.com/ObliviousOdin/loki/releases/tag/v0.1.0-alpha.1) is an unsigned source preview at `12690b426de4610916f91fb42f008391df550f27`. Keep that installation pinned until you deliberately admit a newer version. Development candidates and passing source CI are not a published release or executed update.

```bash
loki --version
loki update --help
loki update --check
```

The source updater belongs to `ObliviousOdin/loki`; its preview default follows `main`. An explicit `loki update` can therefore move away from a release pin. Review the proposed source and preserve configuration, sessions and unfinished source work before applying it. An update check resolves source information; it is not proof that an update was installed. Use the selected release's [owned installation instructions](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/INSTALL.md), not upstream Hermes scripts or update channels.

### Bundled desktop updates

No native app is published in the alpha.1 source release. Packaged automatic updates are disabled until Loki has its own authenticated feed and appropriately signed, qualified artifacts. Do not register an upstream App Installer, Store or macOS updater feed for Loki. A source-built desktop and a packaged app have different update owners; no signing, Store acceptance or downloaded-app update qualification is implied by retained engine support.

### What happens during an update

The inherited source updater coordinates source custody, PM dependency preparation and installation-owned process handoff. It checks the selected source's Loki product identity before accepting it. Preserve data and inspect the actual plan, receipt and diagnostics for your installation. Replacing source files is not a database rollback, and scoped fixture tests are not evidence of a successful live update on every platform.

For an intentionally admitted source update, inspect the available options with `loki update --help`, and validate afterward with:

```bash
loki --version
loki doctor
loki pm status
loki gateway status
```

Check a real provider conversation, resume and any messaging services you use after the change. Those actions require your own configured credentials and acceptance.

### Upgrading to the gateway-owned session runtime

The engine retains gateway-owned sessions across CLI, TUI, desktop and API surfaces. Migration details are advanced architecture reference, not a promise that a live Loki fleet has been migrated. See [gateway-owned runtime](../developer-guide/cron-internals.md) and [multi-profile gateways](../user-guide/multi-profile-gateways.md). Preserve the owning Loki profiles and test the actual services before accepting a migration.

### Manual source maintenance and rollback

Preserve local commits and unfinished work before changing a source checkout; stop the processes you own that use it. Follow that revision's PM bootstrap procedure instead of modifying a managed environment with raw pip. See [developer workflow](../reference/package-management.md#developer-workflow).

A code rollback does not undo configuration or session-store migrations. Keep a coherent pre-update data backup as well as the source revision, and preserve current data before any restore. Do not point different builds at another agent's home. Loki defaults to `~/.loki` on macOS/Linux and `%LOCALAPPDATA%\loki` on Windows; public overrides are `LOKI_HOME` and `LOKI_RUNTIME_DIR`.

### Image and package ownership

Image-, Nix- and package-managed applications must be updated by their actual owner rather than rewritten in place. No public Loki container registry, Termux repository or Store distribution is established by the alpha.1 release. Inherited engine examples naming upstream images or packages are reference material, not Loki update destinations. See [platform scope](./platform-support.md).

## Uninstalling

```bash
loki uninstall --help
```

Review the available removal and dry-run options before choosing them. Preserve user data and backups deliberately; full/data removal is destructive. Stop only the services and applications owned by your Loki installation. Do not delete another agent's homes, unrelated Python processes, project worktrees or shared tool caches.

A source preview does not imply a native package-manager entry. Remove a package through its own manager only if you actually installed that package. See the [owned installation guide](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/INSTALL.md) and [production readiness](https://github.com/ObliviousOdin/loki/blob/main/docs/loki/PRODUCTION-READINESS.md) for the boundary between source capability and qualified distribution.

## Pinned inherited reference

The [original engine update and lifecycle guide](https://github.com/ObliviousOdin/loki/blob/18c525b669b6ea4ba62e6967d228af21d89aa9d3/website/docs/getting-started/updating.md) preserves the advanced upstream guidance at the pinned baseline. Its internal commands, package/update destinations and hosted-service examples are reference material, not Loki installation instructions or service/native qualification. Use the Loki steps above and your selected release's evidence.
