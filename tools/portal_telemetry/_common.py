#!/usr/bin/env python3
"""Common utilities for Portal Ops IQ telemetry tools.

This module provides shared infrastructure for volume and appliance telemetry tools:
- Schema properties for input validation
- Helper functions for data processing and formatting
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from statistics import StatisticsError, mean
from typing import Any, Dict, List, Optional


# ============================================================================
# TIME FIELDS FOR TELEMETRY PARSING
# ============================================================================

_TIME_FIELDS = {
    "time",
    "timestamp",
    "start",
    "start_time",
    "end",
    "end_time",
    "bucket_start",
    "bucket_end",
    "completed_at",
    "created_at",
}

# ============================================================================
# COMMON SCHEMA PROPERTIES (DRY)
# ============================================================================

VOLUME_PROPERTY = {
    "type": "string",
    "description": "Volume name or GUID",
}

PERIOD_PROPERTY_3H = {
    "type": "string",
    "description": "Time period for analysis (default: PT3H)",
    "default": "PT3H",
}

PERIOD_PROPERTY_6H = {
    "type": "string",
    "description": "Time period to analyze (default: PT6H)",
    "default": "PT6H",
}

APPLIANCE_PROPERTY = {
    "type": "string",
    "description": "Appliance name (description) or serial number",
}


# ============================================================================
# PRIVATE HELPER FUNCTIONS
# ============================================================================


def _extract_primary_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract primary data records from a telemetry payload.
    
    Handles two response formats:
    - items: Standard telemetry metrics
    - data_events/metadata_events: Snapshot timeline data
    """
    if not isinstance(payload, dict):
        return []
    
    # Standard format: items list
    if isinstance(payload.get("items"), list):
        return payload["items"]

    # Snapshot timeline format: combine event types
    combined: List[Dict[str, Any]] = []
    for key in ("data_events", "metadata_events"):
        entries = payload.get(key)
        if isinstance(entries, list):
            combined.extend([entry for entry in entries if isinstance(entry, dict)])
    return combined


def _summarize_records(records: List[Dict[str, Any]]) -> str:
    """Generate a summary of telemetry records with statistics."""
    if not records:
        return "No telemetry records returned."

    timestamps: List[Any] = []
    field_samples: Dict[str, List[float]] = {}

    for record in records:
        timestamp = _extract_timestamp(record)
        if timestamp is not None:
            timestamps.append(timestamp)
        for key, value in record.items():
            if key.lower() in _TIME_FIELDS:
                continue
            numeric_value = _coerce_float(value)
            if numeric_value is None:
                continue
            field_samples.setdefault(key, []).append(numeric_value)

    lines: List[str] = [f"Records: {len(records)}"]

    if timestamps:
        try:
            start = _format_timestamp(min(timestamps))
            end = _format_timestamp(max(timestamps))
            lines.append(f"Window: {start} → {end}")
        except Exception:
            pass

    shown = 0
    for field, values in field_samples.items():
        if not values:
            continue
        try:
            avg_val = mean(values)
        except StatisticsError:
            avg_val = values[0]
        try:
            line = (
                f"{field}: avg {avg_val:,.2f} | min {min(values):,.2f} | max {max(values):,.2f}"
            )
        except Exception:
            line = f"{field}: avg {avg_val}"
        lines.append(line)
        shown += 1
        if shown >= 6:
            break

    return "\n".join(lines)


def _format_metadata(metadata: Any) -> str:
    """Format metadata dict as readable string."""
    if not isinstance(metadata, dict) or not metadata:
        return "No metadata provided."
    lines = []
    for idx, (key, value) in enumerate(metadata.items()):
        if idx >= 8:
            lines.append("… (truncated)")
            break
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _raw_preview(payload: Any, limit_chars: int = 1800) -> str:
    """Generate a truncated JSON preview of the payload."""
    try:
        raw = json.dumps(payload, indent=2, default=str)
    except TypeError:
        raw = str(payload)
    if len(raw) > limit_chars:
        raw = raw[:limit_chars] + "\n… (truncated)"
    return raw


def _extract_timestamp(record: Dict[str, Any]) -> Optional[Any]:
    """Extract timestamp from a record using known time field names."""
    for key in _TIME_FIELDS:
        if key in record and record[key] is not None:
            return record[key]
    return None


def _coerce_float(value: Any) -> Optional[float]:
    """Coerce a value to float if possible."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _format_timestamp(value: Any) -> str:
    """Format a timestamp value as ISO 8601 string."""
    if value is None:
        return "Unknown"
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1_000_000_000_000:  # assume ms
            seconds = seconds / 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    return str(value)
