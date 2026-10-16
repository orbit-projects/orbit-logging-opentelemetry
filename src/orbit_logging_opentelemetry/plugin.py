# Copyright 2026-present Orbit Contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Lifecycle-owned OpenTelemetry log export with Orbit context correlation."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping

from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import Logger, LoggerProvider, LogRecordLimits
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from orbit.plugins import ControlAction, ControlResult, Plugin, PluginMetadata

from orbit_logging_opentelemetry.config import OpenTelemetryLoggingConfig

_MAX_ATTRIBUTES = 128
_MAX_ATTRIBUTE_LENGTH = 4_096


class OpenTelemetryLoggingPlugin(Plugin):
    """Export one named Python logger through an isolated OpenTelemetry LoggerProvider.

    The plugin owns the exporter, batch processor, SDK provider, and handler it installs. It never
    mutates OpenTelemetry's global logger provider and never attaches a handler to the root logger
    implicitly.
    """

    metadata = PluginMetadata(
        name="orbit-logging-opentelemetry",
        version="0.1.0a1",
        capabilities=frozenset({"logging.export", "logging.trace-correlation"}),
    )

    def __init__(
        self,
        config: OpenTelemetryLoggingConfig,
        *,
        exporter: LogRecordExporter,
        logger: logging.Logger | None = None,
    ) -> None:
        """Build a bounded batch provider without installing a process-global handler."""
        if not isinstance(config, OpenTelemetryLoggingConfig):
            raise TypeError("config must be OpenTelemetryLoggingConfig.")
        if not isinstance(exporter, LogRecordExporter):
            raise TypeError("exporter must implement OpenTelemetry LogRecordExporter.")
        if logger is not None and not isinstance(logger, logging.Logger):
            raise TypeError("logger must be a standard logging.Logger.")
        self.config = config
        self._logger = logger or logging.getLogger(config.logger_name)
        self._provider = LoggerProvider(
            resource=Resource.create({SERVICE_NAME: config.service_name}),
            shutdown_on_exit=False,
            log_record_limits=LogRecordLimits(
                max_attributes=_MAX_ATTRIBUTES,
                max_attribute_length=_MAX_ATTRIBUTE_LENGTH,
            ),
        )
        self._processor = BatchLogRecordProcessor(
            exporter,
            max_queue_size=config.max_queue_size,
            schedule_delay_millis=config.schedule_delay_millis,
            export_timeout_millis=config.export_timeout_millis,
            max_export_batch_size=config.max_export_batch_size,
        )
        self._provider.add_log_record_processor(self._processor)
        self._otel_logger = self._provider.get_logger("orbit-logging-opentelemetry", "0.1.0a1")
        self._handler = _OrbitLoggingHandler(config.level, self._otel_logger)
        self._closing = False
        self._shutdown_task: asyncio.Task[None] | None = None
        self.control_actions = (
            ControlAction(
                id="flush-logs",
                title="Flush pending logs",
                description="Export queued log records within the configured timeout.",
                handler=self._flush_logs,
            ),
        )

    async def activate(self) -> None:
        """Attach the owned handler to the selected logger during application startup."""
        if self._closing:
            raise RuntimeError("A stopped OpenTelemetry logging plugin cannot be reactivated.")
        if self._handler not in self._logger.handlers:
            self._logger.addHandler(self._handler)

    async def deactivate(self) -> None:
        """Detach the handler and flush/shut down the SDK off the event loop."""
        self._closing = True
        self._logger.removeHandler(self._handler)
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(self._shutdown())
        task = self._shutdown_task
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            raise

    async def _shutdown(self) -> None:
        """Drain and stop the SDK processor within its configured export budget.

        The installed OpenTelemetry SDK 1.45 shutdown call has no timeout parameter and its
        threaded shutdown path can stall on supported Python interpreters. Flush on the SDK's
        bounded processor API, then invoke idempotent shutdown after the queue has drained.
        """
        flushed = await asyncio.to_thread(
            self._processor.force_flush,
            timeout_millis=self.config.export_timeout_millis,
        )
        # The SDK exposes no timeout argument for shutdown. Stop its processor after the bounded
        # flush attempt, then let the provider release its remaining SDK resources.
        self._processor.shutdown()
        self._provider.shutdown()
        if not flushed:
            raise RuntimeError("OpenTelemetry log flush failed.")

    async def _flush_logs(self, _: Mapping[str, object]) -> ControlResult:
        """Flush queued log records off-loop within the configured SDK deadline."""
        if self._closing:
            return ControlResult("Log exporter is shutting down.", succeeded=False)
        flushed = await asyncio.to_thread(
            self._processor.force_flush,
            timeout_millis=self.config.export_timeout_millis,
        )
        return ControlResult(
            "Pending logs were exported."
            if flushed
            else "Log exporter did not flush before its deadline.",
            succeeded=flushed,
        )


class _OrbitLoggingHandler(logging.Handler):
    """Export a log message and allowlisted context without mutating the source record."""

    def __init__(self, level: int, otel_logger: Logger) -> None:
        """Bind one OTel logger to this standard-library logging handler."""
        super().__init__(level)
        self._otel_logger = otel_logger

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a message with bounded Orbit IDs and exception type, never stack text."""
        try:
            attributes = {f"orbit.{key}": value for key, value in self._current_context().items()}
            if record.exc_info and record.exc_info[0] is not None:
                attributes["orbit.exception.type"] = record.exc_info[0].__name__
            created = record.created
            timestamp = int(created * 1_000_000_000) if created > 0 else time.time_ns()
            self._otel_logger.emit(
                timestamp=timestamp,
                severity_number=self._severity(record.levelno),
                severity_text=record.levelname[:64],
                body=record.getMessage()[:_MAX_ATTRIBUTE_LENGTH],
                attributes=attributes,
            )
        except Exception:
            # Do not use logging's default handleError path: it may print arbitrary exporter
            # diagnostics or recurse into the same failing handler.
            return

    @staticmethod
    def _current_context() -> dict[str, str]:
        """Read only validated Orbit request and tracing identifiers."""
        from orbit_logging import current_log_context

        return dict(current_log_context())

    @staticmethod
    def _severity(level: int) -> SeverityNumber:
        """Map standard logging levels to OpenTelemetry severity categories."""
        if level >= logging.CRITICAL:
            return SeverityNumber.FATAL
        if level >= logging.ERROR:
            return SeverityNumber.ERROR
        if level >= logging.WARNING:
            return SeverityNumber.WARN
        if level >= logging.INFO:
            return SeverityNumber.INFO
        return SeverityNumber.DEBUG


__all__ = ["OpenTelemetryLoggingPlugin"]
