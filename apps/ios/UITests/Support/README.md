# Isolated native journey gateway

This developer fixture starts the real dashboard HTTP/native-auth routes,
one-use WS-ticket gate, canonical authority, SQLite store, and `AIAgent` turn
runner. Only upstream identity, model responses and the connector service are
synthetic. It is for simulator and contract qualification, not real execution,
vendor authorization or release acceptance.

Run from the repository with its PM-managed Python environment:

```sh
python apps/ios/UITests/Support/test_gateway.py --ready-file "$TMPDIR/loki-ios-test-ready.json"
```

The ready file contains the random `http://127.0.0.1:<port>` gateway address.
Enter that address through the app's ordinary Gateway setup. Select **Loki UI
Test — local synthetic identity**, then **Continue as test user** in the browser.
The app uses its normal registered `loki-ios` / `com.loki.ios://auth/callback`
flow, token exchange, Keychain and WebSocket connection. There is no special
fixture mode or auth bypass in the shipped application.

The listener binds only `127.0.0.1`, with the real interactive auth gate enabled.
The launcher discards inherited credentials and creates a new temporary user
home, Hermes home, runtime directory and configuration. Ctrl-C or SIGTERM stops
it and removes that state. Restarting creates a new identity/token universe;
sign in again in the app. The ready file contains no bearer or refresh token.
A physical phone cannot reach this loopback-only listener.

Try these messages in the default pet's chat:

| Message | Actual gateway behavior with a synthetic upstream |
| --- | --- |
| `Hello Loki` | Streams a deterministic response and persists the turn. |
| `Show code` | Streams and persists a fenced Swift example with preserved indentation and a closing paragraph. |
| `Ask a question` | Calls the real `clarify` tool. Close and reopen the app to restore the pending question. |
| `Show an approval` | Calls the real terminal tool to remove a disposable folder created inside this fixture's temporary home. Approve or deny through the ordinary control. |
| `Connect HubSpot` | Calls the real connection tool and opens an owner-bound pending card. Use Not now or Continue. No vendor account is connected. |
| `Install test support` | Calls the existing catalog tool and opens a real owner-bound review operation. The source is explicitly synthetic; approving it exercises the installer boundary substitute and downloads no third-party code. Use a test value only in its optional setup field. |

The connection substitute deliberately supplies no vendor URL and never claims
an account connected. Account catalog/vendor-browser completion and voice relay
are outside this fixture. It starts with one default bot and a clearly labeled
synthetic saved memory. The actual multiplex runtime and its periodic profile
watcher allow native Add bot to create and serve another isolated profile. The
fixture does not claim a service-manager process identity or provide a gateway
control socket. Its watcher runs more frequently so tests do not wait for the
ordinary 30-second safety scan. Created bots are real local fixture state.
Cloud relay, real OAuth-provider
availability and device background audio still need their own qualification.

Backend checks launch this same fixture in a fresh subprocess and use actual
HTTP/WebSocket requests:

```sh
scripts/run_tests.sh tests/gateway/test_ios_ui_gateway.py tests/gateway/test_ios_bot_configuration.py -q
```

Use the separate test interpreter described in `CONTRIBUTING.md`. These checks
cover PKCE/state and single-use code, bearer identity, refresh, single-use socket
tickets, profile roster, mobile chat, transcript recovery, replay reset, distinct
subject creation, unserved-profile refusal, restored clarification, approval denial and pending connector
response. The bot configuration check additionally exercises actual profile
creation and serving, metadata CAS refusal, description/instruction isolation,
model inventory, and fingerprinted memory edit/ownership/stale-entry behavior.
`tests/gateway/test_ios_catalog_installation.py` additionally covers the actual
mobile model turn, catalog card, scoped approval, backend outcome and absence of
setup values from the resumed model transcript. Only that fixture's upstream
installer is synthetic; it is not evidence of a real plugin installation.
They do not establish a native simulator run until the iOS app itself
has completed that journey.
