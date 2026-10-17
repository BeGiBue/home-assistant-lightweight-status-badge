# Compatibility and release policy

Before planning or implementing a fundamental mechanism change (for example the
entity importer, configuration workflow, stored rule format or acknowledgement
persistence), explicitly ask the user whether backward compatibility is required.
Ask at the beginning of that work, not only when preparing a release. Preserve a
clear compatibility decision for the agreed scope; do not repeatedly ask the same
question. Before release, clarify compatibility only if it remains undecided or
the scope has materially changed.

The user explicitly confirmed that backward compatibility is not required for
release 0.1.5, including the device/integration entity importer changes.

Do not create a release as part of an implementation task unless the user
explicitly requests it.

# Automatic rule proposals

The device/integration picker proposes rules automatically (rule catalog, then local
analysis, then the manual list). Read `docs/AUTODETECT.md` before touching
`autodetect.py`, `catalog.py`, `catalog.json` or the `autodetect_*` flow steps; it
lists the invariants (no polling or runtime network access, nothing saved without
confirmation, catalog data is untrusted, no guessing of vendor-specific codes).

The user explicitly confirmed that backward compatibility is not required for this
feature scope. `catalog.json` is both the offline fallback and the file clients fetch
from `main`, so review catalog changes like code. Keep `strings.json`,
`translations/en.json` and `translations/de.json` identical in structure.
