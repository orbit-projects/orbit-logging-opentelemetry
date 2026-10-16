# Architecture

The adapter owns one `LoggerProvider`, one bounded `BatchLogRecordProcessor`, one exporter, and
one handler attached to a selected Python logger. All ownership is instance-local. It does not
install OpenTelemetry's global provider or mutate the process root logger implicitly.

The handler converts incoming `LogRecord` instances into OTel records without mutating the source.
It exports only the bounded context exposed by `orbit-logging`, caps message bodies at 4 KiB, and
drops exception text and stack details while retaining the exception class. OpenTelemetry adds
native trace context to records when its context is active. Arbitrary `LogRecord` extras are not
forwarded.

The plugin's configuration bounds queue size, export batch, scheduled delay, and exporter timeout.
Transport settings, credentials, TLS policy, resource detectors, and collector retry behavior
belong to the injected exporter and application deployment.
