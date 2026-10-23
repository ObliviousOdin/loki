# Phone pairing from Loki Desktop

## Source availability and Windows

The reported Windows revision `53e618c` resolves to
`53e618c9ba46e6e7c09a8f74480ee0ceaaccef8c`. That revision has neither the
**Settings → Gateway → Phones** page nor the device-link backend. Its version
string alone does not identify its source: the alpha.1 release tag points to
`12690b426de4610916f91fb42f008391df550f27`, a different revision.

This feature brings the local Desktop management bridge, approved device keys,
bounded public ingress and rendezvous implementation to the public source tree.
It is not restricted to macOS: Windows uses the same canonical gateway and its
OS-local native HTTP owner grants. The dedicated phone-pairing workflow runs
pairing, identity, revocation and Desktop contracts on real Windows, Linux and
macOS runners. Hosted contracts are not a real iPhone/cellular acceptance receipt.

This is a scoped port of the pairing slice from development revision
`5ea4c3d882` plus its native mobile backend prerequisites from `67fd27b5f2`;
it does not merge the development checkout wholesale. Those prerequisites
admit the real `ios` source as a mobile surface (without Electron bridges),
expose connection approval operations, bind registered native callbacks and
preserve idempotent routine creation. Pairing alone without that surface cannot
create a new Bot Chat in the iPhone app. The port preserves public Loki branding,
update ownership, dependency locks and existing CI. Only isolated scripted iOS
test-gateway helpers are included, not the native application, unrelated mobile
improvements, operator configuration or credentials. Use a compatible code-capable
iPhone app; publishing Desktop source cannot update an installed iPhone app.

## Install or update Windows source

Wait for a reviewed merge and successful checks. Replace the placeholder below
with the **full 40-character merged main SHA provided by the maintainer**, not a
PR head, example hash or moving branch. Close Desktop and finish active work
before allowing the supported installer to coordinate the update. Preserve the
existing Loki home; do not delete configuration, credentials or conversations.

Run in PowerShell (Git and the normal supported build prerequisites are needed):

```powershell
$commit = 'REPLACE_WITH_REVIEWED_MERGED_MAIN_SHA'
if ($commit -cnotmatch '^[0-9a-f]{40}$') { throw 'A full reviewed merged SHA is required.' }
$installer = Join-Path $env:TEMP "loki-install-$commit.ps1"
Invoke-WebRequest "https://raw.githubusercontent.com/ObliviousOdin/loki/$commit/scripts/install.ps1" -OutFile $installer
& $installer -Branch main -Commit $commit -NonInteractive -IncludeDesktop
if (-not $?) { throw 'Loki installation did not complete; inspect its error before retrying.' }
loki --version
$homePath = if ($env:LOKI_HOME) { $env:LOKI_HOME } else { Join-Path $env:LOCALAPPDATA 'loki' }
git -C (Join-Path $homePath 'hermes-agent') rev-parse HEAD
loki desktop
```

The pinned installer explicitly admits the commit only if it belongs to the
selected public branch, and `-IncludeDesktop` requests the Desktop rebuild.
Verify the printed source revision equals `$commit`; merely seeing `0.1.0a1`
is insufficient. If PowerShell policy blocks the script, inspect the downloaded
script and use your organization's approved policy; do not disable security
policy globally. A refusal due to active work, local changes or update custody
must be resolved through the supported recovery path, not `git reset --hard`.

## A visible Phones page is not configured transport

Each host needs its **own** stable HTTPS phone ingress, bound to that host's
public key. Installing this source does not borrow another computer's tunnel,
operator secret or pairing state. Do not point a Windows host at a Mac's ingress
and expect the Windows bots to execute there.

An operator must provide:

- A stable named outbound TLS tunnel to the dedicated loopback-only phone ingress
  (`127.0.0.1:9450` by default), not the canonical gateway/control listener.
- An owned rendezvous deployment from `apps/phone-link-service`, restricted to
  exact approved gateway origins. See its [README](../../apps/phone-link-service/README.md).
- Non-secret configuration through `loki config set`:
  `dashboard.device_links.gateway_url`, `rendezvous_url`, `host_name`,
  `ingress_port` and finally `enabled=true`.
- `LOKI_PHONE_LINK_REGISTRATION_TOKEN` through the host's protected secret
  workflow. The selected launch home's credential scope must own it; never put
  it in YAML, command arguments, Git, a phone build or chat.
- An existing dashboard owner sign-in provider. Desktop retains this explicit
  approval session in memory, not in the renderer. Password providers use the
  local browser form; OAuth uses the operator's existing validated callback
  origin. Keep `dashboard.public_url` unchanged.

Start the ingress through the managed launcher:

```powershell
loki --run-module hermes_cli.phone_ingress
```

Coordinate canonical gateway restart through the supported lifecycle after
changing captured configuration. Keep the computer awake and online. There is
no automatic tunnel provisioning or `phones install-service` command in this
slice. Missing configuration fails closed and does not generate an invitation.

Once readiness and owner sign-in are verified, choose **Connect an iPhone**,
enter its expiring code in the compatible iPhone app, compare both screens and
approve that exact phone. The phone receives owner-equivalent dashboard access
to this home, including served bot profiles, files and tools; this is not a
restricted guest role. Revoking one phone closes its channels and refuses its
credentials without deleting conversations or disconnecting other devices.

## Updates, tags and remaining release gates

`loki update` is a source updater for **ObliviousOdin/loki**, with channel choice
and source-identity validation. The public preview defaults to `main`; a saved
explicit channel may differ. An explicit installer `-Commit` pin selects that
exact installation revision; it is not a promise that future updates stay pinned.
A `main` merge neither creates a tag nor edits an existing immutable release.
The current published release remains alpha.1 until a separate release is made.

Packaged automatic updates are deliberately disabled pending an owned
authenticated feed and signed artifacts. The current public preview workflow
packages exact merged source and optionally unsigned macOS artifacts; it does
not build a Windows distributable. Inherited upstream publication workflows are
repository-guarded and must not be repurposed by removing ownership checks.
Windows signing, native packaged install/update acceptance and distribution are
separate gates, **not prerequisites for the source-update command above**.

Existing dependency-security work is tracked separately in PR #9. This port does
not suppress advisory findings, relax release-age policies, or represent those
unmerged patches as present. Before release, resolve that security gate and
verify the final combined head, plus actual phone onboarding, renewal/revocation,
Wi-Fi/cellular behavior and public ingress operation on the intended host.
