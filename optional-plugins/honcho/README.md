# Honcho memory for Loki

This optional compatibility copy preserves the Honcho provider from
Plastic Labs' pinned Hermes integration. See [UPSTREAM.json](UPSTREAM.json),
[LICENSE](LICENSE), and [UPSTREAM-README.md](UPSTREAM-README.md) for provenance,
copyright, and the original provider documentation.

Install through `loki plugins install honcho`, then configure it with
`loki memory setup honcho`. The Loki repository is private, so Git must have
explicitly configured read access to `ObliviousOdin/loki`. Installation uses
the normal catalog pin, security scan, dependency consent, and PM publication.
The plugin is optional and is not automatically activated by being shipped
in the source tree. No Honcho subscription or credentials are included.

The SDK is a declared plugin dependency. If setup finds it missing, it offers
to repair the current PM dependency environment, preserving enabled plugins
and selected extras. Setup continues only after the SDK imports; a generation
that cannot be adopted safely requires restarting Loki.

The default host, workspace, and AI peer are `loki`, or `loki_<profile>` for
a named profile. Configuration belongs to the active Loki home's
`honcho.json`; an existing Loki root file can hold explicitly configured
profile host blocks. Explicit host, workspace, peer, server, and session
settings in those files retain their values. The provider never falls back
to `~/.honcho`, Hermes, or Fabric state. Copying or selecting another
application's configuration is an explicit operator action.

Use your own Honcho API key or self-hosted server. OAuth requires an
application authorized for Loki, configured through
`auth.oauth_clients.honcho.client_id` in Loki's `config.yaml` or this
profile's `HONCHO_OAUTH_CLIENT_ID`. Configure the application's redirect
URI for the loopback flow. The upstream Hermes OAuth application is not
reused. API-key setup is the default; browser and device flows remain
available after explicit OAuth configuration.

Fallback diagnostics retain call stacks and exception class names while
omitting provider exception messages, which can contain credentials or
response data. Namespace, configuration, SDK-constructor, and installation
tests use synthetic state and a network-free SDK double. Real Honcho
service, subscription, and OAuth flows require external configuration and
are not qualified by those tests.
