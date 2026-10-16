# Orbit Logging OpenTelemetry

`orbit-logging-opentelemetry` exports records from one explicitly selected Python logger through
an isolated OpenTelemetry Logs SDK provider. It depends on [`orbit-logging`](../orbit-logging) for
structured logging context and does not install a process-global provider or modify the root
logger unless the caller explicitly selects it.

**Status:** unpublished v0.1.0-alpha review candidate. Local tests use the OpenTelemetry in-memory
exporter; OTLP collector connectivity and hosted CI are separate release gates.

## Install

```bash
python -m pip install 'orbit-logging-opentelemetry[otlp-http]'
```

For gRPC OTLP, install the `otlp-grpc` extra. Construct the SDK exporter and pass it to
`OpenTelemetryLoggingPlugin`; transport endpoints, TLS, credentials, and exporter configuration
remain application-owned.

## Configure

```python
import logging
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from orbit_logging_opentelemetry import OpenTelemetryLoggingConfig, OpenTelemetryLoggingPlugin

plugin = OpenTelemetryLoggingPlugin(
    OpenTelemetryLoggingConfig(service_name="orders-api", logger_name="orders"),
    exporter=OTLPLogExporter(),
    logger=logging.getLogger("orders"),
)
application.register_plugin(plugin)
```

The plugin attaches a bounded batch processor during application activation and flushes it on
shutdown. Exported records include validated Orbit application, request, correlation, trace, and
span IDs currently bound to the task. The handler also picks up the active OpenTelemetry trace
context. Exception messages and stack traces are omitted; only the exception class is retained.
The handler caps exported message bodies at 4 KiB. Application log messages may still contain
sensitive data, so callers must redact them before logging.

The plugin contributes a **Flush pending logs** action to Orbit CLI. The synchronous SDK flush runs
off the event loop and uses the configured export timeout. The action reports a sanitized success or
failure result without exposing exporter details.

## Boundaries

This adapter does not configure HTTP instrumentation, sampling, resource detectors, collector
pipelines, credentials, or exporter retry policies. Keep one service identity consistent across
logs, metrics, and traces. Use the general `orbit-logging` contract when OTel export is not needed.

## Development

```bash
python -m pip install -e '.[dev]'
pytest
ruff check src tests
ruff format --check src tests
mypy
python -m build
```

See [architecture](docs/architecture/overview.md), [operations](docs/operations/README.md),
[security](docs/security/overview.md), and [development](docs/development/README.md). Licensed
under Apache-2.0.
