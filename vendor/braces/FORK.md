# Private braces build dependency

This private package is derived from braces 3.0.3. Its original name, author
credits, README and MIT license are retained. `UPSTREAM.json` records the exact
registry archive, integrity, Git revision and original file hashes. It is not an
upstream release and is not intended for registry publication.

GHSA-vfj7-8cjw-p6xm remains unpatched upstream. This fork replaces input-driven
recursion in compile, stringify, expansion, append and flatten with explicit
frames. Existing character and range limits remain. Valid deeply nested inputs
are processed without introducing a new nesting cap. Cyclic AST children and
cyclic nested arrays are refused with `ERR_BRACES_CYCLE`. This does not make
arbitrary regular expressions or unbounded Cartesian expansion safe.

Expansion queues follow the actual child traversal. Public upstream PR 82
(https://github.com/micromatch/braces/pull/82, head
1f11eb558be9ea0cda87861408bb766e2e714086, Passpass92) highlighted this invariant.
The iterative implementation here does not adopt that proposal's fixed depth
or visit caps, range-step changes, or range-node mutation changes.

`node vendor/braces/archive.mjs --write` creates the deterministic private
archive. Regeneration requires updating the website lockfile to its new SRI.
`node vendor/braces/archive.mjs --check` must run before dependency preparation
or packaging: it compares source bytes, the archive and the website lock SRI.
A warm npm cache alone does not verify changed local archive bytes.

Only website consumers are currently overridden. The local archive is a normal
copied npm dependency, not a live directory link. Run the package tests after
website `npm ci`, then the website typecheck and complete English build.
