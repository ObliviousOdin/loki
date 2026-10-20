# Private htmlparser2 dependency

This is a private MIT fork of htmlparser2 12.0.0. The original package name,
authors, exports, TypeScript declarations, source, README and license are
retained. `UPSTREAM.json` records the original registry archive, SRI, Git
revision and every original file hash. This is not an upstream release and
must not be published to a registry.

GHSA-x3q4-9hxx-gx8m documents two ways a noscript discard region can expose
content. sanitize-html 2.18.0 fixes the implied-close case, but its published
CDATA variant still reproduces with htmlparser2 12.0.0, including when using
sanitize-html 2.18.1. This fork gates the tokenizer CDATA predicate to XML, the parser's existing
foreign-content context, or the existing explicit `recognizeCDATA: true` option.
The option is carried into the tokenizer so its public ParserOptions contract
continues to work. Ordinary
HTML declarations become bogus comments ending at the next `>`, allowing
the sanitizer to see the noscript region. XML, SVG and MathML retain the
upstream CDATA path. No depth cap, preprocessing step or parser API is added.
The low-level foreign-context callback remains optional, as upstream declares.

Only the sanitizer's root dependency is overridden. The documentation website
has no override for this fork. The registry sanitizer remains at 2.18.0; later
upstream releases must be tested against both published cases before removing
this mitigation. No new Loki source vulnerability is asserted by these tests.

The modified TypeScript predicate and compiled JavaScript correspond. The
JavaScript and source map were regenerated with the repository's TypeScript
6.0.3; that compiler reproduces the original JavaScript exactly before the fix.
Only the tokenizer source, compiled JavaScript, corresponding declarations and
source maps change; other upstream runtime and declaration files are unchanged.

`node vendor/htmlparser2/archive.mjs --write` creates a deterministic private
archive with fixed owners, modes and clocks. A changed archive requires a new
private version and lock SRI. `--check` joins the corresponding source, archive,
root manifest selection and lock SRI before dependency preparation; root
`preinstall` runs it during normal npm installation. `--check-installed` also
compares every installed package file. A warm cache alone is insufficient.

Run the canonical sanitizer contracts, the parser context tests, the actual
sanitizer consumer checks and the complete root CI after installation. Scanner
responses do not qualify this owned mitigation or prove GitHub alert closure.
