#!/usr/bin/env python3
"""Share-related data models."""

from typing import Dict, Any, List
from models.base import BaseModel, NestedModel


class Share(BaseModel):
    """SMB/CIFS share model."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.guid = data.get("guid", "")
        self.volume_guid = data.get("volume_guid", "")
        self.filer_serial_number = data.get("filer_serial_number", "")
        self.share_name = data.get("share_name", "")
        self.path = data.get("path", "")
        self.comment = data.get("comment", "")
        self.readonly = data.get("readonly", False)
        self.browseable = data.get("browseable", True)
        self.enable_mobile_access = data.get("enable_mobile_access", False)
        self.enable_browser_access = data.get("enable_browser_access", False)
        self.enable_previous_vers = data.get("enable_previous_vers", False)  # Previous versions field
        self.browser_access_readonly = data.get("browser_access_readonly", False)
        self.vetoed_files = data.get("vetoed_files", "")
        self.links = data.get("links", {})
        
        # Additional fields that might be present
        self.enable_snapshots = data.get("enable_snapshots", False)
        self.snapshot_policy = data.get("snapshot_policy", "")
        self.audit_enabled = data.get("audit_enabled", False)
        self.hidden = data.get("hidden", False)
    
    @property
    def is_readonly(self) -> bool:
        """Check if share is read-only."""
        return self.readonly
    
    @property
    def is_readwrite(self) -> bool:
        """Check if share is read-write."""
        return not self.readonly
    
    @property
    def has_browser_access(self) -> bool:
        """Check if browser access is enabled."""
        return self.enable_browser_access
    
    @property
    def has_mobile_access(self) -> bool:
        """Check if mobile access is enabled."""
        return self.enable_mobile_access
    
    @property
    def has_previous_versions(self) -> bool:
        """Check if previous versions are enabled."""
        return self.enable_previous_vers
    
    @property
    def is_root_share(self) -> bool:
        """Check if this is a root share."""
        return self.path == "/" or self.path == "\\" or self.path == ""
    
    @property
    def access_methods(self) -> List[str]:
        """Get list of access methods."""
        methods = ["SMB/CIFS"]
        if self.has_browser_access:
            methods.append("Browser")
        if self.has_mobile_access:
            methods.append("Mobile")
        return methods
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get a summary dictionary with key information."""
        return {
            "guid": self.guid,
            "share_name": self.share_name,
            "volume_guid": self.volume_guid,
            "filer_serial_number": self.filer_serial_number,
            "path": self.path,
            "comment": self.comment,
            "readonly": self.readonly,
            "browseable": self.browseable,
            "enable_mobile_access": self.enable_mobile_access,
            "enable_browser_access": self.enable_browser_access,
            "enable_previous_vers": self.enable_previous_vers,
            "has_previous_versions": self.has_previous_versions,
            "browser_access_readonly": self.browser_access_readonly,
            "vetoed_files": self.vetoed_files,
            "is_root_share": self.is_root_share,
            "access_methods": self.access_methods,
            "audit_enabled": self.audit_enabled,
            "hidden": self.hidden
        }