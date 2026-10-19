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

Nix evaluation, builds, module activation, and packaged desktop launch have
not been qualified for this preview. The development host has no Nix
installation; static review and Python helper compilation do not establish
Nix compatibility. Run `nix flake check` and the host's actual installation
tests before relying on these outputs.
