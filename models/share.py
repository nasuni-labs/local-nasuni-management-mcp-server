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
        self.share_name = data.get("name", "")  # API uses "name", not "share_name"
        self.path = data.get("path", "")
        self.comment = data.get("comment", "")
        self.readonly = data.get("readonly", False)
        self.browseable = data.get("browseable", True)
        
        self.enable_mobile_access = data.get("mobile", False)  # API uses "mobile"
        self.enable_browser_access = data.get("browser_access", False)  # API uses "browser_access"
        self.enable_previous_vers = data.get("enable_previous_vers", False)  # This is correct
        
        self.browser_access_readonly = data.get("browser_access_readonly", False)
        self.vetoed_files = data.get("veto_files", "")
        self.links = data.get("links", {})
        
        self.enable_snapshots = data.get("enable_snapshots", False)
        self.snapshot_policy = data.get("snapshot_policy", "")
        self.audit_enabled = data.get("audit_enabled", False)
        self.hidden = data.get("hidden", False)
        self.case_sensitive = data.get("case_sensitive", False)
        self.enable_snapshot_dirs = data.get("enable_snapshot_dirs", False)
        self.hide_unreadable = data.get("hide_unreadable", False)
        self.hosts_allow = data.get("hosts_allow", "")
        self.aio_enabled = data.get("aio_enabled", True)
        self.fruit_enabled = data.get("fruit_enabled", False)
        self.smb_encrypt = data.get("smb_encrypt", "")
    
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
            "name": self.share_name,  # Use consistent naming
            "share_name": self.share_name,
            "volume_guid": self.volume_guid,
            "filer_serial_number": self.filer_serial_number,
            "path": self.path,
            "comment": self.comment,
            "readonly": self.readonly,
            "permission": "Read-Only" if self.readonly else "Read-Write",
            "browseable": self.browseable,
            
            # Use the internal field names (these should work now):
            "enable_mobile_access": self.enable_mobile_access,
            "enable_browser_access": self.enable_browser_access,
            "enable_previous_vers": self.enable_previous_vers,
            
            # Also provide the property names for backward compatibility:
            "mobile_access": self.has_mobile_access,
            "browser_access": self.has_browser_access,
            "has_previous_versions": self.has_previous_versions,
            
            "browser_access_readonly": self.browser_access_readonly,
            "veto_files": self.vetoed_files,
            "is_root_share": self.is_root_share,
            "access_methods": self.access_methods,
            "audit_enabled": self.audit_enabled,
            "hidden": self.hidden
        }