# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Real OTEL instruments for the three metrics the design doc requires.

Previously these were faked as `logging.info("prompt_amender_..._total",
extra={...})` calls -- the stdlib formatter never renders `extra` fields
unless a custom Formatter reads them, so no metric was ever actually
emitted. This module creates real counters/histograms via the OTEL Metrics
API; the SDK/exporter wiring (OTLP endpoint, etc.) is configured once at
process startup in `service_callout_example.py`.
"""
from opentelemetry import metrics

_meter = metrics.get_meter("prompt_amender")

requests_total = _meter.create_counter(
    "prompt_amender_requests_total",
    description="Requests processed by the Prompt-Amender ext_proc filter",
)

amend_latency_seconds = _meter.create_histogram(
    "prompt_amender_amend_latency_seconds",
    description="Latency of prompt amendment processing",
    unit="s",
)

config_reloads_total = _meter.create_counter(
    "prompt_amender_config_reloads_total",
    description="Configuration reload attempts",
)
