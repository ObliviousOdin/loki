# Loki with Nix

From an authenticated checkout:

```sh
nix build .#loki
./result/bin/loki --help
nix develop
loki --version
```

`default` and `loki` select the full upstream feature closure. `minimal`,
`messaging`, `desktop`, `tui`, and `web` remain available as separate outputs.
The overlay exports `pkgs.loki`. Python's distribution is
`obliviousodin-loki-agent`; internal Hermes Python modules remain unchanged.

The Home Manager module uses `programs.loki` for installation and
`services.loki` for configuration and daemons:

```nix
programs.loki = {
  enable = true;
  desktop.enable = true;
};
services.loki = {
  enable = true;
  gateway.enable = true;
  lokiHome = "${config.home.homeDirectory}/.loki";
  workingDirectory = "${config.home.homeDirectory}/workspace";
};
```

The NixOS module also uses `services.loki`; its default state directory is
`/var/lib/loki`, with application data in `/var/lib/loki/.loki`. Home Manager
defaults to `~/.loki`. The gateway and backend have `loki-gateway` and
`loki-backend` unit names. Container users and state bridges use Loki names.
Activation does not migrate or link Hermes or Fabric user data.

Public environment settings use `LOKI_*`. The package wrapper translates
the shared assembler's internal environment map into that namespace before
the Loki entrypoint binds its runtime. Dependencies remain pinned by the
existing `flake.lock`, `uv.lock`, npm lock, and PM lock.

A [Linux component diagnostic](https://github.com/ObliviousOdin/loki/actions/runs/39540959987)
qualified the reviewed node-gyp dependency graph, its supplier suite and lint,
installation, and a native addon compiled and loaded with Node 26.5. The supplier
suite itself ran under Node 24.18.0 and retained six pending cases. The same run
built the local browser component with its declared setuptools 84 backend and
verified installed version, Pillow requirement and license metadata. Its backend
is a build-only input; the runtime lock and dev-only setuptools 83 are unchanged.

The full Nix environment, module activation and packaged desktop launch remain
unqualified. The development host has no Nix installation. Run `nix flake check`
and the host's actual installation tests before relying on those outputs.
