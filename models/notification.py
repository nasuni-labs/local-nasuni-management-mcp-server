#!/usr/bin/env python3
"""Notification data model."""

from typing import Dict, Any, Optional
from datetime import datetime
from models.base import BaseModel


class Notification(BaseModel):
    """Notification model."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.id = data.get("id", 0)
        self.date = data.get("date", "")
        self.priority = data.get("priority", "")
        self.name = data.get("name", "")
        self.message = data.get("message", "")
        self.group = data.get("group", "")
        self.acknowledged = data.get("acknowledged", False)
        self.sticky = data.get("sticky", False)
        self.urgent = data.get("urgent", False)
        self.origin = data.get("origin", "")
        self.links = data.get("links", {})
    
    @property
    def datetime_obj(self) -> Optional[datetime]:
        """Get datetime object from date string."""
        try:
            # Parse format like "2025-08-12T02:18:36UTC"
            date_str = self.date.replace("UTC", "Z")
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except:
            return None
    
    @property
    def is_error(self) -> bool:
        """Check if this is an error notification."""
        return self.priority in ["error", "critical", "alert"]
    
    @property
    def is_warning(self) -> bool:
        """Check if this is a warning notification."""
        return self.priority in ["warning", "warn"]
    
    @property
    def is_info(self) -> bool:
        """Check if this is an info notification."""
        return self.priority in ["info", "notice"]
    
    @property
    def filer_serial(self) -> Optional[str]:
        """Extract filer serial from links if available."""
        filer_link = self.links.get("filer", {}).get("href", "")
        if "/filers/" in filer_link:
            parts = filer_link.split("/filers/")
            if len(parts) > 1:
                return parts[1].rstrip("/")
        return None
    
    @property
    def volume_name(self) -> Optional[str]:
        """Extract volume name from message if present."""
        # Common patterns: "volume Volume1", "volume VolDemoOpsIQ"
        if "volume" in self.message.lower():
            import re
            # Look for "volume SomeName" pattern
            match = re.search(r'volume\s+([^:\s]+)', self.message, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    @property
    def notification_type(self) -> str:
        """Get notification type category."""
        name_upper = self.name.upper()
        if "AV_" in name_upper or "ANTIVIRUS" in name_upper:
            return "Antivirus"
        elif "LICENSE" in name_upper:
            return "License"
        elif "SNAPSHOT" in name_upper:
            return "Snapshot"
        elif "REPLICATION" in name_upper:
            return "Replication"
        elif "CACHE" in name_upper:
            return "Cache"
        elif "QUOTA" in name_upper:
            return "Quota"
        elif "AUTH" in name_upper or "LOGIN" in name_upper:
            return "Authentication"
        elif "NETWORK" in name_upper or "CONNECTION" in name_upper:
            return "Network"
        else:
            return "General"
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get a summary dictionary with key information."""
        return {
            "id": self.id,
            "date": self.date,
            "priority": self.priority,
            "name": self.name,
            "message": self.message,
            "group": self.group,
            "acknowledged": self.acknowledged,
            "urgent": self.urgent,
            "origin": self.origin,
            "filer_serial": self.filer_serial,
            "volume_name": self.volume_name,
            "notification_type": self.notification_type,
            "is_error": self.is_error,
            "is_warning": self.is_warning,
            "is_info": self.is_info
        }