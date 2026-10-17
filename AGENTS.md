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
