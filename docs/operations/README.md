# Operations

Select a named application logger and configure an OTLP exporter explicitly. Set the same
`service.name` across signal adapters. Run a local collector before enabling remote export and
verify TLS, endpoint authentication, network egress, queue sizing, and shutdown budgets in the
deployment environment.

The batch queue is bounded. If the exporter cannot keep up, records can be dropped by the SDK;
this plugin does not persist logs or guarantee delivery. Alert on collector-side dropped records
and exporter health. Do not place secrets or request bodies in log messages or attributes.
