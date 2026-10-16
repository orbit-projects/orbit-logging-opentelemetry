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
"""Verify safe logging export and cross-signal trace correlation."""

import logging
from uuid import uuid4

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from orbit.runtime.context import (
    bind_correlation_id,
    bind_request_id,
    reset_correlation_id,
    reset_request_id,
)

from orbit_logging_opentelemetry import OpenTelemetryLoggingConfig, OpenTelemetryLoggingPlugin


async def test_plugin_exports_context_and_omits_exception_text() -> None:
    exporter = InMemoryLogRecordExporter()
    logger = logging.getLogger("orbit.tests.otel.logs")
    plugin = OpenTelemetryLoggingPlugin(
        OpenTelemetryLoggingConfig(
            service_name="orbit-tests",
            logger_name="orbit.tests.otel.logs",
            schedule_delay_millis=50,
            max_queue_size=32,
            max_export_batch_size=16,
        ),
        exporter=exporter,
        logger=logger,
    )
    await plugin.activate()
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        request_token = bind_request_id(uuid4())
        correlation_token = bind_correlation_id("corr-456")
        try:
            try:
                raise RuntimeError("sensitive-value-must-not-export")
            except RuntimeError:
                logger.exception("operation failed")
        finally:
            reset_correlation_id(correlation_token)
            reset_request_id(request_token)
        result = await plugin.control_actions[0].handler({})
        assert result is not None and result.succeeded
        await plugin.deactivate()
        records = exporter.get_finished_logs()
        assert len(records) == 1
        record = records[0].log_record
        attributes = dict(record.attributes or {})
        assert attributes["orbit.request.id"]
        assert attributes["orbit.correlation.id"] == "corr-456"
        assert attributes["orbit.exception.type"] == "RuntimeError"
        assert "sensitive-value-must-not-export" not in str(record)
        assert "sensitive-value-must-not-export" not in str(attributes)
    finally:
        logger.setLevel(original_level)
        await plugin.deactivate()


def test_config_rejects_invalid_queue_bounds() -> None:
    with pytest.raises(ValueError):
        OpenTelemetryLoggingConfig(max_queue_size=1, max_export_batch_size=2)
