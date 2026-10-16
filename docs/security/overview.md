# Security

The adapter avoids global logger/provider mutation, does not mutate input records, bounds message
bodies and OpenTelemetry attributes, excludes exception messages and stacks, and does not include
exporter exception text in its own diagnostics. Orbit request and trace identifiers may still be sensitive
operational metadata; protect telemetry transport and storage accordingly.

The adapter cannot redact arbitrary application log messages, prevent exporters from retaining
records, select a secure OTLP endpoint, or configure TLS and authentication for a collector. Keep
credentials outside source and logs, use authenticated encrypted transport, and apply retention and
access controls at the telemetry backend.
