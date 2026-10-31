# Smart home for Loki

Connect an existing Home Assistant instance to one Loki profile. This optional capability
starts read-only and accesses only exact, explicitly allowed lights and switches. It is
not installed or enabled by updating Loki.

In Loki 0.1.0-alpha.2 or later, install `smart-home` from Capabilities > Plugins after
reviewing the package. Open its settings with the gear button. The existing settings form
provides the Home Assistant address, a masked token field, the entity allowlist, and a
control switch. Saving settings does not connect to Home Assistant.

1. Set up Home Assistant separately and add compatible devices using its integrations.
2. Enter its base address. HTTPS is accepted; HTTP is limited to a local IP, localhost,
   or a `.local` hostname. Redirects and environment proxies are not used.
3. Enter a dedicated Home Assistant access token privately in the masked field. Loki
   stores it in this profile's secret store as `LOKI_SMART_HOME_TOKEN`. Never paste it
   into a chat, a URL, a plugin file, or `config.yaml`.
4. In Home Assistant, find the exact entity IDs for the desired lights or switches.
   Set Allowed lights and switches to a JSON list such as `["light.kitchen", "switch.lamp"]`.
   An empty list permits no device reads or writes. Camera and lock entities are refused.
5. Ask Loki to check the smart-home connection, then read the allowed devices. These are
   explicit read-only calls. Verify the names and states before enabling changes.
6. Optionally enable Allow confirmed changes. Every on/off request reads the target first
   and then opens a fresh host approval. Only a current approve-once response authorizes
   that one request. Approvals off, yolo, saved approvals, and unattended policy cannot
   authorize these changes. If the execution surface cannot present that confirmation,
   the operation stays blocked.

`smart_home_status` shows configuration state and the setup checklist without connecting.
`smart_home_check` explicitly tests the API. `smart_home_read` returns only entity ID,
friendly name and state for the allowed scope; omit the ID to read that configured scope.
`smart_home_set_state` accepts only one exact entity ID and `on` or `off`. There is no
arbitrary service, scene, script, brightness, lock, alarm, camera, or automation control.

An unavailable device blocks writes. A settings change while approval is pending cancels
the request. If a write response is lost or the server fails, the result says the outcome
is unknown and does not retry. Check the physical device or read its state before deciding
what to do next. An accepted request is reported as submitted, not proof the device changed.

The allowlist is enforced by this capability, not by the Home Assistant token itself.
Use a dedicated account and do not enable a second unrestricted control integration if
you need this boundary. This plugin does not grant permissions to other Loki tools or
sandbox trusted local code. Isolated plugin-host processes may lack a confirmation viewer;
controls then fail closed. Read-only tools and settings remain available.

The capability does not import a Google Home household, discover the LAN, install Home
Assistant, fetch a camera stream, or set up a Reolink camera. Configure those integrations
separately before offering devices to Loki. No real-device acceptance is claimed by the
mock-based tests.
