#!/usr/bin/env python3
"""Portal Ops IQ telemetry API clients covering appliance and volume metrics."""

from __future__ import annotations

from typing import Dict, Any, List, Optional

from api.portal_base_client import PortalBaseAPIClient
from config.logging_setup import get_logger
from models.data_propagation import DataPropagationEvent, DataPropagationAnalysis
from models.data_protection import DataProtectionSnapshot, DataProtectionAnalysis
from models.portal_telemetry_models import (
    DataSnapshotEvent,
    MetadataSnapshotEvent,
    SnapshotTimelineAnalysis,
)

logger = get_logger(__name__)


APPLIANCE_TELEMETRY_CONFIG: Dict[str, Dict[str, Any]] = {
    "load_average": {
        "path": "load_average",
        "display_name": "CPU Load Average",
        "description": "1/5/15 minute load averages compared against appliance core count.",
        "request_type": "standard",
    },
    "cache_disk_io_time": {
        "path": "cache_disk_io_time",
        "display_name": "Cache Disk Latency",
        "description": "Read/write latency for cache disks (ms).",
        "request_type": "standard",
    },
    "cache_disk_io_latency": {
        "path": "cache_disk_io_latency",
        "display_name": "Cache Disk IO Latency",
        "description": "Read/write IO latency for cache disks (ms).",
        "request_type": "standard",
    },
    "cache_disk_iops": {
        "path": "cache_disk_iops",
        "display_name": "Cache Disk IOPS",
        "description": "Read/write IOPS observed on cache disks.",
        "request_type": "standard",
    },
    "cache_hits_misses": {
        "path": "cache_hits_misses",
        "display_name": "Cache Hits & Misses",
        "description": "Cache hit/miss distribution used to size cache tiers.",
        "request_type": "standard",
    },
    "cache_utilization": {
        "path": "cache_utilization",
        "display_name": "Cache Utilization",
        "description": "Percent of cache capacity consumed over time.",
        "request_type": "standard",
    },
    "cow_disk_iops": {
        "path": "cow_disk_iops",
        "display_name": "CoW Disk IOPS",
        "description": "Copy-on-Write disk IOPS for metadata operations.",
        "request_type": "standard",
    },
    "cow_disk_io_time": {
        "path": "cow_disk_io_time",
        "display_name": "CoW Disk Latency",
        "description": "Copy-on-Write disk latency (ms).",
        "request_type": "standard",
    },
    "file_iq_disk_iops": {
        "path": "file_iq_disk_iops",
        "display_name": "File IQ DB IOPS",
        "description": "I/O profile for File IQ databases.",
        "request_type": "standard",
    },
    "file_iq_disk_io_time": {
        "path": "file_iq_disk_io_time",
        "display_name": "File IQ DB Latency",
        "description": "Latency for File IQ database disks.",
        "request_type": "standard",
    },
    "cpu_utilization": {
        "path": "cpu_utilization",
        "display_name": "CPU Utilization",
        "description": "[PORTAL - PREFERRED FOR CPU METRICS] CPU usage percent across the appliance. Use this instead of NMC health tools for CPU status.",
        "request_type": "standard",
    },
    "memory_utilization": {
        "path": "memory_utilization",
        "display_name": "Memory Utilization",
        "description": "[PORTAL - PREFERRED FOR MEMORY METRICS] Overall memory consumption and trends. Use this instead of NMC health tools for memory status.",
        "request_type": "standard",
    },
    "memory_utilization_details": {
        "path": "memory_utilization_details",
        "display_name": "Memory Breakdown",
        "description": "Detailed memory breakdown (page cache, slab, processes).",
        "request_type": "standard",
    },
    "network_utilization": {
        "path": "network_utilization",
        "display_name": "Network Throughput",
        "description": "Inbound/outbound throughput across NICs.",
        "request_type": "standard",
    },
    "os_disk_io_time": {
        "path": "os_disk_io_time",
        "display_name": "OS Disk Latency",
        "description": "Latency metrics for OS volumes.",
        "request_type": "standard",
    },
    "os_disk_iops": {
        "path": "os_disk_iops",
        "display_name": "OS Disk IOPS",
        "description": "Read/write IOPS on the OS disk set.",
        "request_type": "standard",
    },
    "smb_connections": {
        "path": "smb_connections",
        "display_name": "SMB Sessions",
        "description": "Concurrent SMB client connections.",
        "request_type": "standard",
    },
    "current_appliance_performance": {
        "path": "current_appliance_performance",
        "display_name": "Current Appliance Performance",
        "description": "[PORTAL - PREFERRED FOR HEALTH] Quick appliance performance health check. USE THIS FIRST for appliance health questions. Returns CPU, memory, I/O stress metrics efficiently.",
        "request_type": "duration",
    },
    "appliance_health_score": {
        "path": "appliance_health_score",
        "display_name": "Appliance Health Score",
        "description": "[PORTAL - USE ONLY IF MORE DETAIL NEEDED] Deeper health analysis with anomaly detection. EXPENSIVE CALL - only use when user explicitly needs anomaly detection or detailed health scoring beyond current_appliance_performance.",
        "request_type": "health",
    },
}


VOLUME_TELEMETRY_CONFIG: Dict[str, Dict[str, Any]] = {
    "lock_utilization": {
        "path": "lock_utilization",
        "display_name": "Core Protection",
        "description": "Lock utilization and core protection windows per volume.",
    },
    "average_time_to_protect": {
        "path": "average_time_to_protect",
        "display_name": "Average Time to Protect",
        "description": "Mean time to complete protection cycles.",
    },
    "snapshot_timeline": {
        "path": "snapshot_timeline",
        "display_name": "Snapshot Timeline",
        "description": "[PORTAL - PREFERRED FOR SNAPSHOT STATUS] Data/metadata push phases for each snapshot. Use this instead of NMC snapshot health tools.",
    },
    "snapshot_content": {
        "path": "snapshot_content",
        "display_name": "Snapshot Content",
        "description": "Object/file counts captured per snapshot.",
    },
    "oldest_unprotected_data": {
        "path": "oldest_unprotected_data",
        "display_name": "Oldest Unprotected Data",
        "description": "[PORTAL - PREFERRED FOR PROTECTION STATUS] OUD trend for the selected volume. Use this instead of NMC protection summary tools.",
    },
    "snapshot_details": {
        "path": "snapshot_details",
        "display_name": "Snapshot Details",
        "description": "[PORTAL - PREFERRED FOR SNAPSHOT INFO] Detailed per-snapshot timing + metadata. Use this instead of NMC snapshot tools.",
    },
    "snapshot_propagation_by_appliance": {
        "path": "snapshot_propagation_by_appliance",
        "display_name": "Snapshot Propagation by Appliance",
        "description": "Sync timing by appliance for recent snapshots.",
    },
}


class PortalApplianceTelemetryAPIClient(PortalBaseAPIClient):
    """Client for Portal Ops IQ appliance telemetry endpoints."""

    async def get_metric(
        self,
        serial_number: str,
        metric: str,
        period: str = "PT3H",
        panel_width: Optional[int] = None,
        bin_size: Optional[int] = None,
        timezone_offset_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch a telemetry metric for a single appliance."""
        metric_key = metric.strip().lower()
        if metric_key not in APPLIANCE_TELEMETRY_CONFIG:
            raise ValueError(f"Unsupported appliance telemetry metric: {metric}")

        config = APPLIANCE_TELEMETRY_CONFIG[metric_key]
        endpoint = f"/telemetry/appliances/{serial_number}/{config['path']}"
        payload = self._build_payload(
            config.get("request_type", "standard"),
            period=period,
            panel_width=panel_width,
            bin_size=bin_size,
            timezone_offset_minutes=timezone_offset_minutes,
        )

        logger.info(
            "Fetching Portal appliance telemetry",
            extra={
                "metric": metric_key,
                "serial": serial_number,
                "period": period,
            }
        )

        response = await self.post(endpoint, json=payload)
        return response

    def _build_payload(
        self,
        request_type: str,
        period: str,
        panel_width: Optional[int],
        bin_size: Optional[int],
        timezone_offset_minutes: Optional[int],
    ) -> Dict[str, Any]:
        """Build request payload per schema type."""
        if request_type == "health":
            payload = {"period": period}
            if timezone_offset_minutes is not None:
                payload["timezone_offset_minutes"] = timezone_offset_minutes
            return payload
        if request_type == "duration":
            return {"period": period}

        payload: Dict[str, Any] = {"period": period}
        if panel_width is not None:
            payload["panel_width"] = panel_width
        if bin_size is not None:
            payload["bin_size"] = bin_size
        return payload

    async def test_connection(self) -> bool:
        """Test basic connectivity by ensuring authentication works."""
        try:
            return await self._ensure_authenticated()
        except Exception:
            return False


class PortalVolumeTelemetryAPIClient(PortalBaseAPIClient):
    """Client for Portal Ops IQ volume telemetry endpoints."""

    async def get_metric(
        self,
        volume_guid: str,
        metric: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        chart_width: Optional[int] = None,
        smart_sampling: Optional[bool] = True,
    ) -> Dict[str, Any]:
        """Fetch a telemetry metric for a Portal volume."""
        metric_key = metric.strip().lower()
        if metric_key not in VOLUME_TELEMETRY_CONFIG:
            raise ValueError(f"Unsupported volume telemetry metric: {metric}")

        self._require_serial_numbers(serial_numbers)

        payload = self._build_volume_payload(
            serial_numbers=serial_numbers,
            period=period,
            chart_width=chart_width,
            smart_sampling=smart_sampling,
        )

        endpoint = f"/telemetry/volumes/{volume_guid}/{VOLUME_TELEMETRY_CONFIG[metric_key]['path']}"

        logger.info(
            "Fetching Portal volume telemetry",
            extra={
                "metric": metric_key,
                "volume": volume_guid,
                "serial_count": len(serial_numbers),
                "period": period,
            }
        )

        response = await self.post(endpoint, json=payload)
        self._log_volume_metric_response(metric_key, response)
        return response

    @staticmethod
    def _require_serial_numbers(serial_numbers: List[str]) -> None:
        if not serial_numbers:
            raise ValueError("At least one serial number is required for volume telemetry")

    def _build_volume_payload(
        self,
        serial_numbers: List[str],
        period: str,
        chart_width: Optional[int],
        smart_sampling: Optional[bool],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "period": period,
            "serial_numbers": serial_numbers,
        }
        if chart_width is not None:
            payload["chart_width"] = chart_width
        if smart_sampling is not None:
            payload["smart_sampling"] = smart_sampling
        return payload

    def _log_volume_metric_response(
        self,
        metric: str,
        response: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata: Dict[str, Any] = {"metric": metric}
        if extra:
            metadata.update(extra)

        if "error" in response:
            logger.error(
                "Portal volume telemetry error",
                extra={**metadata, "details": response.get("error")},
            )
            return

        if isinstance(response.get("items"), list):
            metadata["item_count"] = len(response["items"])
        if isinstance(response.get("data_events"), list):
            metadata["data_events"] = len(response["data_events"])
        if isinstance(response.get("metadata_events"), list):
            metadata["metadata_events"] = len(response["metadata_events"])
        if isinstance(response.get("snapshot_appliances"), list):
            metadata["snapshot_appliances"] = len(response["snapshot_appliances"])
        if isinstance(response.get("sync_appliances"), list):
            metadata["sync_appliances"] = len(response["sync_appliances"])
        if isinstance(response.get("appliance_count"), int):
            metadata["appliance_count"] = response["appliance_count"]

        logger.info(
            "Retrieved Portal volume telemetry data",
            extra=metadata,
        )

    async def get_volume_data_protection(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True,
        chart_width: int = 1000,
    ) -> Dict[str, Any]:
        """Fetch raw data protection snapshots (data_propagation_raw endpoint)."""
        self._require_serial_numbers(serial_numbers)
        endpoint = f"/telemetry/volumes/{volume_guid}/data_propagation_raw"
        payload = self._build_volume_payload(
            serial_numbers=serial_numbers,
            period=period,
            chart_width=chart_width,
            smart_sampling=smart_sampling,
        )

        logger.info(
            "Fetching Portal volume data protection telemetry",
            extra={
                "volume": volume_guid,
                "serial_count": len(serial_numbers),
                "period": period,
            },
        )

        response = await self.post(endpoint, json=payload)
        self._log_volume_metric_response("data_protection_raw", response)
        return response

    async def get_volume_data_protection_analysis(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True,
    ) -> DataProtectionAnalysis:
        """Parse data protection telemetry into DataProtectionAnalysis."""
        response = await self.get_volume_data_protection(
            volume_guid=volume_guid,
            serial_numbers=serial_numbers,
            period=period,
            smart_sampling=smart_sampling,
        )

        if "error" in response:
            logger.error(
                "Portal data protection telemetry error",
                extra={"volume": volume_guid, "details": response["error"]},
            )
            return DataProtectionAnalysis([], {})

        snapshots: List[DataProtectionSnapshot] = []
        for item in response.get("items", []):
            try:
                snapshots.append(DataProtectionSnapshot(item))
            except Exception as exc:  # pragma: no cover - defensive parsing
                logger.warning(f"Failed to parse data protection snapshot: {exc}")

        metadata = response.get("metadata", {})
        logger.info(
            "Parsed data protection snapshots",
            extra={"count": len(snapshots)},
        )
        return DataProtectionAnalysis(snapshots, metadata)

    async def get_volume_data_propagation(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True,
        chart_width: int = 1000,
    ) -> Dict[str, Any]:
        """Fetch data propagation timing (snapshot_propagation_by_appliance endpoint)."""
        self._require_serial_numbers(serial_numbers)
        endpoint = f"/telemetry/volumes/{volume_guid}/snapshot_propagation_by_appliance"
        payload = self._build_volume_payload(
            serial_numbers=serial_numbers,
            period=period,
            chart_width=chart_width,
            smart_sampling=smart_sampling,
        )

        response = await self.post(endpoint, json=payload)
        self._log_volume_metric_response("snapshot_propagation_by_appliance", response)
        return response

    async def get_volume_data_propagation_analysis(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True,
    ) -> DataPropagationAnalysis:
        """Parse propagation telemetry into DataPropagationAnalysis."""
        response = await self.get_volume_data_propagation(
            volume_guid=volume_guid,
            serial_numbers=serial_numbers,
            period=period,
            smart_sampling=smart_sampling,
        )

        if "error" in response:
            logger.error(
                "Portal data propagation telemetry error",
                extra={"volume": volume_guid, "details": response["error"]},
            )
            return DataPropagationAnalysis([], {})

        events: List[DataPropagationEvent] = []
        for item in response.get("items", []):
            try:
                events.append(DataPropagationEvent(item))
            except Exception as exc:  # pragma: no cover - defensive parsing
                logger.warning(f"Failed to parse data propagation event: {exc}")

        metadata = {
            "snapshot_appliances": response.get("snapshot_appliances", []),
            "sync_appliances": response.get("sync_appliances", []),
        }

        logger.info(
            "Parsed data propagation events",
            extra={"count": len(events)},
        )
        return DataPropagationAnalysis(events, metadata)

    async def get_volume_snapshot_timeline(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True,
        chart_width: int = 1000,
    ) -> Dict[str, Any]:
        """Fetch snapshot timeline data for a volume."""
        self._require_serial_numbers(serial_numbers)
        endpoint = f"/telemetry/volumes/{volume_guid}/snapshot_timeline"
        payload = self._build_volume_payload(
            serial_numbers=serial_numbers,
            period=period,
            chart_width=chart_width,
            smart_sampling=smart_sampling,
        )

        response = await self.post(endpoint, json=payload)
        self._log_volume_metric_response("snapshot_timeline", response)
        return response

    async def get_volume_snapshot_timeline_analysis(
        self,
        volume_guid: str,
        serial_numbers: List[str],
        period: str = "PT3H",
        smart_sampling: bool = True,
    ) -> SnapshotTimelineAnalysis:
        """Parse snapshot timeline telemetry into SnapshotTimelineAnalysis."""
        response = await self.get_volume_snapshot_timeline(
            volume_guid=volume_guid,
            serial_numbers=serial_numbers,
            period=period,
            smart_sampling=smart_sampling,
        )

        if "error" in response:
            logger.error(
                "Portal snapshot timeline telemetry error",
                extra={"volume": volume_guid, "details": response["error"]},
            )
            return SnapshotTimelineAnalysis([], [], {})

        data_events: List[DataSnapshotEvent] = []
        for event in response.get("data_events", []):
            try:
                data_events.append(DataSnapshotEvent(event))
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Failed to parse data snapshot event: {exc}")

        metadata_events: List[MetadataSnapshotEvent] = []
        for event in response.get("metadata_events", []):
            try:
                metadata_events.append(MetadataSnapshotEvent(event))
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Failed to parse metadata snapshot event: {exc}")

        metadata = {
            "appliance_count": response.get("appliance_count", 0),
            "min_time": response.get("min_time", 0),
            "max_time": response.get("max_time", 0),
        }

        logger.info(
            "Parsed snapshot timeline events",
            extra={
                "data_events": len(data_events),
                "metadata_events": len(metadata_events),
            },
        )
        return SnapshotTimelineAnalysis(data_events, metadata_events, metadata)

    async def test_connection(self) -> bool:
        """Test basic connectivity by ensuring authentication works."""
        try:
            return await self._ensure_authenticated()
        except Exception:
            return False


__all__ = [
    "APPLIANCE_TELEMETRY_CONFIG",
    "VOLUME_TELEMETRY_CONFIG",
    "PortalApplianceTelemetryAPIClient",
    "PortalVolumeTelemetryAPIClient",
]
