#!/usr/bin/env python3
"""Volume-filer connection data models."""

from typing import Dict, Any, List
from models.base import BaseModel


class VolumeConnection(BaseModel):
    """Volume-filer connection model."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.connected = data.get("connected", False)
        self.volume_guid = data.get("volume_guid", "")
        self.filer_serial_number = data.get("filer_serial_number", "")
        self.links = data.get("links", {})
    
    @property
    def is_connected(self) -> bool:
        """Check if volume is connected to filer."""
        return self.connected
    
    @property
    def is_disconnected(self) -> bool:
        """Check if volume is disconnected from filer."""
        return not self.connected
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get a summary dictionary with key information."""
        return {
            "volume_guid": self.volume_guid,
            "filer_serial_number": self.filer_serial_number,
            "connected": self.connected,
            "status": "Connected" if self.connected else "Disconnected"
        }