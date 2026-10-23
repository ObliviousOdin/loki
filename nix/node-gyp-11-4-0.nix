{
  buildNpmPackage,
  fetchFromGitHub,
  nodejs,
  lib,
}:

let
  node-gyp-11_4_0 = buildNpmPackage rec {
    pname = "node-gyp";
    version = "11.4.0";

    src = fetchFromGitHub {
      owner = "nodejs";
      repo = "node-gyp";
      rev = "refs/tags/v${version}";
      hash = "sha256-VtomUV+0kTp34IuS0D0dR4ZMWpk4Ptpk1CBP8rdW2a4=";
    };

    postPatch = ''
      # Retain the supplier suite while moving its vulnerable Mocha 11 tool graph.
      substituteInPlace package.json \
        --replace-fail '"mocha": "^11.0.1"' '"mocha": "^12.0.3"'
      ln -s ${./node-gyp-11-4-0-package-lock.json} package-lock.json
    '';

    # Verified fetcher-v2 dependency cache for the reviewed lockfile.
    npmDepsHash = "sha256-MSuUFJS+2q6OjYzJRNkQsAdlNlAjm2A5gDCnUR6btSQ=";

    npmDepsFetcherVersion = 2;

    dontNpmBuild = true;

    makeWrapperArgs = [ "--set npm_config_nodedir ${nodejs}" ];

    meta = {
      description = "Node.js native addon build tool";
      homepage = "https://github.com/nodejs/node-gyp";
      license = lib.licenses.mit;
      mainProgram = "node-gyp";
    };
  };
in
node-gyp-11_4_0
