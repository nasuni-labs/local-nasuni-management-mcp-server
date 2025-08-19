#!/usr/bin/env python3
"""Volume-related data models."""

from typing import Dict, Any, List
from models.base import BaseModel, NestedModel


class Provider(NestedModel):
    """Cloud provider information."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.name = data.get("name", "")
        self.shortname = data.get("shortname", "")
        self.location = data.get("location", "")
        self.storage_class = data.get("storage_class")
        self.cred_uuid = data.get("cred_uuid", "")


class AntivirusService(NestedModel):
    """Antivirus service configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.enabled = data.get("enabled", False)
        self.days = data.get("days", {})
        self.check_files_immediately = data.get("check_files_immediately", False)
        self.allday = data.get("allday", True)
        self.start = data.get("start", 0)
        self.stop = data.get("stop", 0)
        self.frequency = data.get("frequency", 300)
    
    @property
    def active_days(self) -> List[str]:
        """Get list of days when antivirus is active."""
        return [day for day, active in self.days.items() if active]


class Protocols(NestedModel):
    """Protocol configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.permissions_policy = data.get("permissions_policy", "")
        self.protocols = data.get("protocols", [])
    
    @property
    def protocol_list(self) -> str:
        """Get comma-separated list of protocols."""
        return ", ".join(self.protocols)


class FilerAccess(NestedModel):
    """Individual filer access permission."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.filer_guid = data.get("filer_guid", "")
        self.permission = data.get("permission", "")
    
    @property
    def is_enabled(self) -> bool:
        """Check if access is enabled."""
        return self.permission != "disabled"


class RemoteAccess(NestedModel):
    """Remote access configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.enabled = data.get("enabled", False)
        self.access_permissions = data.get("access_permissions", "")
        self.filer_access = [
            FilerAccess(access) for access in data.get("filer_access", [])
        ]
    
    @property
    def enabled_filers(self) -> List[FilerAccess]:
        """Get list of filers with enabled access."""
        return [access for access in self.filer_access if access.is_enabled]
    
    @property
    def readonly_filers(self) -> List[FilerAccess]:
        """Get list of filers with readonly access."""
        return [access for access in self.filer_access if access.permission == "readonly"]
    
    @property
    def readwrite_filers(self) -> List[FilerAccess]:
        """Get list of filers with readwrite access."""
        return [access for access in self.filer_access if access.permission == "readwrite"]


class SnapshotRetention(NestedModel):
    """Snapshot retention policy."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.retain = data.get("retain", "")
    
    @property
    def is_infinite(self) -> bool:
        """Check if retention is infinite."""
        return self.retain.upper() == "INFINITE"


class CloudIO(NestedModel):
    """Cloud I/O configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.compression = data.get("compression", False)
        self.chunk_size = data.get("chunk_size", 0)


class Auth(NestedModel):
    """Authentication configuration."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.authenticated_access = data.get("authenticated_access", True)
        self.policy = data.get("policy", "")
        self.policy_label = data.get("policy_label", "")
    
    @property
    def is_public(self) -> bool:
        """Check if volume has public access."""
        return self.policy == "public" or not self.authenticated_access


class Volume(BaseModel):
    """Main volume model."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.guid = data.get("guid", "")
        self.filer_serial_number = data.get("filer_serial_number", "")
        self.nmc_managed = data.get("nmc_managed", False)
        self.provider = Provider(data.get("provider", {}))
        self.antivirus_service = AntivirusService(data.get("antivirus_service", {}))
        self.name = data.get("name", "")
        self.protocols = Protocols(data.get("protocols", {}))
        self.remote_access = RemoteAccess(data.get("remote_access", {}))
        self.snapshot_retention = SnapshotRetention(data.get("snapshot_retention", {}))
        self.quota = data.get("quota", 0)
        self.cloud_io = CloudIO(data.get("cloud_io", {}))
        self.auth = Auth(data.get("auth", {})) if "auth" in data else None
        self.case_sensitive = data.get("case_sensitive", False)
        self.links = data.get("links", {})
        
    
    @property
    def quota_gb(self) -> float:
        """Get quota in GB."""
        return self.quota / 1024 if self.quota > 0 else 0
    
    @property
    def has_quota(self) -> bool:
        """Check if volume has a quota set."""
        return self.quota > 0
    
    @property
    def is_cifs(self) -> bool:
        """Check if volume supports CIFS."""
        return "CIFS" in self.protocols.protocols
    
    @property
    def is_nfs(self) -> bool:
        """Check if volume supports NFS."""
        return "NFS" in self.protocols.protocols
    
    @property
    def antivirus_enabled(self) -> bool:
        """Check if antivirus is enabled."""
        return self.antivirus_service.enabled
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get a summary dictionary with key information."""
        return {
            "guid": self.guid,
            "name": self.name,
            "filer_serial_number": self.filer_serial_number,
            "nmc_managed": self.nmc_managed,
            "provider_name": self.provider.name,
            "provider_location": self.provider.location,
            "protocols": self.protocols.protocol_list,
            "quota_gb": self.quota_gb,
            "has_quota": self.has_quota,
            "case_sensitive": self.case_sensitive,
            "antivirus_enabled": self.antivirus_enabled,
            "remote_access_enabled": self.remote_access.enabled,
            "compression_enabled": self.cloud_io.compression,
            "authenticated_access": self.auth.authenticated_access if self.auth else True,
            "is_public": self.auth.is_public if self.auth else False,
            "retention_infinite": self.snapshot_retention.is_infinite,
            "enabled_filers_count": len(self.remote_access.enabled_filers),
            "readonly_filers_count": len(self.remote_access.readonly_filers),
            "readwrite_filers_count": len(self.remote_access.readwrite_filers),
        }