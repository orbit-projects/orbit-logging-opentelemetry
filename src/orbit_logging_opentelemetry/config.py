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
"""Validated resource identity and bounded OpenTelemetry log batching settings."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationInfo,
    field_validator,
)


class OpenTelemetryLoggingConfig(BaseModel):
    """Configuration for one isolated logger provider and one explicitly named logger."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, validate_default=True)

    service_name: StrictStr = Field(min_length=1, max_length=255)
    logger_name: StrictStr = Field(min_length=1, max_length=255)
    level: StrictInt = Field(default=20, ge=0, le=50)
    max_queue_size: StrictInt = Field(default=2_048, ge=1, le=100_000)
    schedule_delay_millis: StrictInt = Field(default=5_000, ge=1, le=300_000)
    export_timeout_millis: StrictInt = Field(default=10_000, ge=1, le=120_000)
    max_export_batch_size: StrictInt = Field(default=512, ge=1, le=10_000)

    @field_validator("service_name", "logger_name")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        """Reject whitespace-only or control-bearing resource and logger names."""
        if not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Telemetry identity values must be non-empty printable text.")
        return value

    @field_validator("max_export_batch_size")
    @classmethod
    def validate_batch_limit(cls, value: int, info: ValidationInfo) -> int:
        """Keep each export batch within the configured queue capacity."""
        queue_size = info.data.get("max_queue_size", 2_048)
        if value > queue_size:
            raise ValueError("max_export_batch_size cannot exceed max_queue_size.")
        return value
