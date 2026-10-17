# Home Assistant Lightweight Status Badge

An event-driven Home Assistant status monitor with graphical rule management,
localized fault explanations and global acknowledgements.

Development branch: backend from PR #6 plus GUI rule management for issue #3.
The dashboard badge, detail dialog and secondary alert UI remain in development;
this is not a release of the complete badge product.

For a development HA installation, copy `custom_components/lightweight_status_badge`
into its `custom_components` directory, restart HA and add **Lightweight Status
Badge** under **Settings → Devices & services**. Open **Configure** to manage
rules using HA entity selectors. No Helpers entry or recurring YAML edits.

- [Graphical configuration and navigation](docs/GUI.md)
- [Backend contract and automated test commands](docs/BACKEND.md)
- [Product specification](SPEC.md)
- [Architecture](ARCHITECTURE.md)

Validated target: Home Assistant 2026.10.2 with Python 3.14. HACS/release validation,
physical-device checks and Raspberry Pi measurements remain follow-up work.
