# Certificate template

The predefined certificate design is implemented in code
(`app/services/certificate_service.py`, ReportLab) rather than as a binary
`.pdf` template: the layout (border, headings, recipient/event/issuer fields,
certificate ID) is fixed, and per-recipient data is rendered into it.

No template editor is in scope for this assignment.
