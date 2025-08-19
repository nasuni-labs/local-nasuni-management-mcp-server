#!/usr/bin/env python3
"""Volume-Filer Details data models."""

from typing import Dict, Any, List
from datetime import datetime
from models.base import BaseModel, NestedModel


class SyncSchedule(NestedModel):
    """Sync schedule configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.days = data.get("days", {})
        self.allday = data.get("allday", True)
        self.start = data.get("start", 0)
        self.stop = data.get("stop", 0)
        self.frequency = data.get("frequency", 300)
        self.auto_cache_allowed = data.get("auto_cache_allowed", True)
        self.auto_cache_min_file_size = data.get("auto_cache_min_file_size", 0)
    
    @property
    def active_days(self) -> List[str]:
        """Get list of days when sync is active."""
        return [day for day, active in self.days.items() if active]
    
    @property
    def frequency_minutes(self) -> float:
        """Get sync frequency in minutes."""
        return self.frequency / 60 if self.frequency > 0 else 0
    
    @property
    def schedule_summary(self) -> str:
        """Get human-readable schedule summary."""
        if self.allday:
            return f"All day, every {self.frequency_minutes:.1f} minutes"
        else:
            return f"From {self.start}:00 to {self.stop}:00, every {self.frequency_minutes:.1f} minutes"


class SnapshotSchedule(NestedModel):
    """Snapshot schedule configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.days = data.get("days", {})
        self.allday = data.get("allday", True)
        self.start = data.get("start", 0)
        self.stop = data.get("stop", 0)
        self.frequency = data.get("frequency", 300)
    
    @property
    def active_days(self) -> List[str]:
        """Get list of days when snapshots are active."""
        return [day for day, active in self.days.items() if active]
    
    @property
    def frequency_minutes(self) -> float:
        """Get snapshot frequency in minutes."""
        return self.frequency / 60 if self.frequency > 0 else 0
    
    @property
    def is_enabled(self) -> bool:
        """Check if snapshot schedule is enabled."""
        return any(self.days.values()) and self.frequency > 0


class FileAlertsService(NestedModel):
    """File alerts service configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.enabled = data.get("enabled", False)


class AuditingLogs(NestedModel):
    """Auditing logs configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.prune_audit_logs = data.get("prune_audit_logs", True)
        self.days_to_keep = data.get("days_to_keep", 90)
        self.exclude_by_default = data.get("exclude_by_default", False)
        self.include_takes_priority = data.get("include_takes_priority", True)
        self.include_patterns = data.get("include_patterns", [])
        self.exclude_patterns = data.get("exclude_patterns", [])
        self.user_blacklist = data.get("user_blacklist", [])
        self.protocol_whitelist = data.get("protocol_whitelist", [])


class AuditingEvents(NestedModel):
    """Auditing events configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.create = data.get("create", True)
        self.delete = data.get("delete", True)
        self.rename = data.get("rename", True)
        self.close = data.get("close", True)
        self.security = data.get("security", True)
        self.metadata = data.get("metadata", True)
        self.write = data.get("write", True)
        self.read = data.get("read", True)
    
    @property
    def enabled_events(self) -> List[str]:
        """Get list of enabled event types."""
        events = []
        for event_type in ["create", "delete", "rename", "close", "security", "metadata", "write", "read"]:
            if getattr(self, event_type, False):
                events.append(event_type)
        return events
    
    @property
    def all_events_enabled(self) -> bool:
        """Check if all event types are enabled."""
        return all([self.create, self.delete, self.rename, self.close, 
                   self.security, self.metadata, self.write, self.read])


class Auditing(NestedModel):
    """Auditing configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.enabled = data.get("enabled", False)
        self.collapse = data.get("collapse", True)
        self.events = AuditingEvents(data.get("events", {}))
        self.logs = AuditingLogs(data.get("logs", {}))
        self.syslog_export = data.get("syslog_export", False)
        self.output_type = data.get("output_type", "csv")
        self.destination = data.get("destination", "")
    
    @property
    def retention_summary(self) -> str:
        """Get audit retention summary."""
        if self.logs.prune_audit_logs:
            return f"Keep {self.logs.days_to_keep} days"
        else:
            return "Keep indefinitely"


class VolumeFilerStatus(NestedModel):
    """Volume-filer connection status."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.accessible_data = data.get("accessible_data", 0)
        self.data_not_yet_protected = data.get("data_not_yet_protected", 0)
        self.first_snapshot = data.get("first_snapshot", "")
        self.last_snapshot = data.get("last_snapshot", "")
        self.last_snapshot_start = data.get("last_snapshot_start", "")
        self.last_snapshot_end = data.get("last_snapshot_end", "")
        self.last_snapshot_version = data.get("last_snapshot_version", 0)
        self.snapshot_status = data.get("snapshot_status", "unknown")
        self.snapshot_percent = data.get("snapshot_percent", 0)
        self.ftp_dir_count = data.get("ftp_dir_count", 0)
        self.export_count = data.get("export_count", 0)
        self.share_count = data.get("share_count", 0)
    
    @property
    def accessible_data_gb(self) -> float:
        """Get accessible data in GB."""
        return self.accessible_data / (1024**3) if self.accessible_data > 0 else 0
    
    @property
    def data_not_yet_protected_gb(self) -> float:
        """Get unprotected data in GB."""
        return self.data_not_yet_protected / (1024**3) if self.data_not_yet_protected > 0 else 0
    
    @property
    def has_unprotected_data(self) -> bool:
        """Check if there's unprotected data."""
        return self.data_not_yet_protected > 0
    
    @property
    def first_snapshot_datetime(self) -> datetime:
        """Get first snapshot as datetime object."""
        try:
            return datetime.fromisoformat(self.first_snapshot.replace("UTC", "+00:00"))
        except:
            return None
    
    @property
    def last_snapshot_datetime(self) -> datetime:
        """Get last snapshot as datetime object."""
        try:
            return datetime.fromisoformat(self.last_snapshot.replace("UTC", "+00:00"))
        except:
            return None
    
    @property
    def is_snapshot_active(self) -> bool:
        """Check if snapshot is currently running."""
        return self.snapshot_status in ["running", "active", "in_progress"]
    
    @property
    def is_snapshot_idle(self) -> bool:
        """Check if snapshot is idle."""
        return self.snapshot_status == "idle"
    
    @property
    def total_services(self) -> int:
        """Get total count of services (shares + exports + ftp)."""
        return self.share_count + self.export_count + self.ftp_dir_count
    
    @property
    def protection_percentage(self) -> float:
        """Get percentage of data that is protected."""
        total_data = self.accessible_data + self.data_not_yet_protected
        if total_data == 0:
            return 100.0
        return (self.accessible_data / total_data) * 100


class VolumeFilerDetails(BaseModel):
    """Volume-Filer connection details model."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.guid = data.get("guid", "")
        self.filer_serial_number = data.get("filer_serial_number", "")
        self.name = data.get("name", "")
        self.type = data.get("type", "")
        self.sync_schedule = SyncSchedule(data.get("sync_schedule", {}))
        self.snapshot_schedule = SnapshotSchedule(data.get("snapshot_schedule", {}))
        self.snapshot_access = data.get("snapshot_access", False)
        self.file_alerts_service = FileAlertsService(data.get("file_alerts_service", {}))
        self.auditing = Auditing(data.get("auditing", {}))
        self.status = VolumeFilerStatus(data.get("status", {}))
        self.links = data.get("links", {})
    
    @property
    def volume_guid(self) -> str:
        """Extract volume GUID from full GUID."""
        # The guid appears to be in format "volume_guid_number"
        parts = self.guid.split("_")
        return "_".join(parts[:-1]) if len(parts) > 1 else self.guid
    
    @property
    def is_master(self) -> bool:
        """Check if this is a master volume."""
        return self.type.lower() == "master"
    
    @property
    def is_cache(self) -> bool:
        """Check if this is a cache volume."""
        return self.type.lower() == "cache"
    
    @property
    def has_snapshot_schedule(self) -> bool:
        """Check if snapshot schedule is configured."""
        return self.snapshot_schedule.is_enabled
    
    @property
    def has_active_auditing(self) -> bool:
        """Check if auditing is enabled and configured."""
        return self.auditing.enabled and len(self.auditing.events.enabled_events) > 0
    
    @property
    def data_protection_status(self) -> str:
        """Get overall data protection status."""
        if self.status.has_unprotected_data:
            return f"At Risk ({self.status.protection_percentage:.1f}% protected)"
        else:
            return "Fully Protected"
    
    @property
    def service_summary(self) -> str:
        """Get summary of services configured."""
        services = []
        if self.status.share_count > 0:
            services.append(f"{self.status.share_count} shares")
        if self.status.export_count > 0:
            services.append(f"{self.status.export_count} exports")
        if self.status.ftp_dir_count > 0:
            services.append(f"{self.status.ftp_dir_count} FTP dirs")
        
        return ", ".join(services) if services else "No services"
    
    @property
    def security_features_summary(self) -> Dict[str, bool]:
        """Get summary of enabled security features."""
        return {
            "auditing": self.auditing.enabled,
            "file_alerts": self.file_alerts_service.enabled,
            "snapshot_access": self.snapshot_access,
            "syslog_export": self.auditing.syslog_export if self.auditing.enabled else False
        }
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get a summary dictionary with key information."""
        return {
            "guid": self.guid,
            "volume_guid": self.volume_guid,
            "name": self.name,
            "filer_serial_number": self.filer_serial_number,
            "type": self.type,
            "is_master": self.is_master,
            "accessible_data_gb": self.status.accessible_data_gb,
            "unprotected_data_gb": self.status.data_not_yet_protected_gb,
            "protection_percentage": self.status.protection_percentage,
            "data_protection_status": self.data_protection_status,
            "snapshot_enabled": self.has_snapshot_schedule,
            "snapshot_status": self.status.snapshot_status,
            "last_snapshot": self.status.last_snapshot,
            "auditing_enabled": self.auditing.enabled,
            "file_alerts_enabled": self.file_alerts_service.enabled,
            "snapshot_access_enabled": self.snapshot_access,
            "service_summary": self.service_summary,
            "total_services": self.status.total_services,
            "share_count": self.status.share_count,
            "export_count": self.status.export_count,
            "ftp_dir_count": self.status.ftp_dir_count,
            "sync_schedule_summary": self.sync_schedule.schedule_summary,
            "auditing_retention": self.auditing.retention_summary if self.auditing.enabled else "N/A",
            "security_features": self.security_features_summary
        }