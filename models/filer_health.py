#!/usr/bin/env python3
"""Filer health data models."""

from typing import Dict, Any, List, Optional
from datetime import datetime
from models.base import BaseModel


class FilerHealth(BaseModel):
    """Filer health status model."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.filer_serial_number = data.get("filer_serial_number", "")
        self.last_updated = data.get("last_updated", "")
        
        # Core system health components
        self.network = data.get("network", "")
        self.memory = data.get("memory", "")
        self.cpu = data.get("cpu", "")
        self.disk = data.get("disk", "")
        self.filesystem = data.get("filesystem", "")
        self.services = data.get("services", "")
        
        # File services health
        self.nfs = data.get("nfs", "")
        self.smb = data.get("smb", "")
        self.directoryservices = data.get("directoryservices", "")
        
        # Advanced features health
        self.cyberresilience = data.get("cyberresilience", "")
        self.fileaccelerator = data.get("fileaccelerator", "")
        self.agfl = data.get("agfl", "")  # Advanced Global File Locking
        self.nasuni_iq = data.get("nasuni_iq", "")  # File IQ
        
        self.links = data.get("links", {})
    
    @property
    def last_updated_datetime(self) -> Optional[datetime]:
        """Parse the last updated timestamp."""
        if not self.last_updated:
            return None
        try:
            # Handle UTC format: "2025-08-08T16:37:47UTC"
            timestamp_str = self.last_updated.replace("UTC", "+00:00")
            return datetime.fromisoformat(timestamp_str)
        except (ValueError, AttributeError):
            return None
    
    @property
    def overall_health_status(self) -> str:
        """Determine overall health status based on all components."""
        health_components = [
            self.network, self.memory, self.cpu, self.disk, 
            self.filesystem, self.services, self.nfs, self.smb,
            self.directoryservices, self.cyberresilience, 
            self.fileaccelerator, self.agfl, self.nasuni_iq
        ]
        
        # Filter out empty and "No Results" statuses
        active_components = [
            comp for comp in health_components 
            if comp and comp not in ["", "No Results"]
        ]
        
        if not active_components:
            return "Unknown"
        
        # If any component is unhealthy, overall status is unhealthy
        if any(comp == "Unhealthy" for comp in active_components):
            return "Unhealthy"
        
        # If all active components are healthy, overall status is healthy
        if all(comp == "Healthy" for comp in active_components):
            return "Healthy"
        
        # Mixed or unknown states
        return "Warning"
    
    @property
    def is_healthy(self) -> bool:
        """Check if filer is completely healthy."""
        return self.overall_health_status == "Healthy"
    
    @property
    def is_unhealthy(self) -> bool:
        """Check if filer has unhealthy components."""
        return self.overall_health_status == "Unhealthy"
    
    @property
    def has_warnings(self) -> bool:
        """Check if filer has warning conditions."""
        return self.overall_health_status == "Warning"
    
    @property
    def unhealthy_components(self) -> List[str]:
        """Get list of unhealthy components."""
        components = {
            "Network": self.network,
            "Memory": self.memory,
            "CPU": self.cpu,
            "Disk": self.disk,
            "Filesystem": self.filesystem,
            "Services": self.services,
            "NFS": self.nfs,
            "SMB": self.smb,
            "Directory Services": self.directoryservices,
            "Cyber Resilience": self.cyberresilience,
            "File Accelerator": self.fileaccelerator,
            "Advanced Global File Locking": self.agfl,
            "File IQ": self.nasuni_iq
        }
        
        return [name for name, status in components.items() if status == "Unhealthy"]
    
    @property
    def healthy_components(self) -> List[str]:
        """Get list of healthy components."""
        components = {
            "Network": self.network,
            "Memory": self.memory,
            "CPU": self.cpu,
            "Disk": self.disk,
            "Filesystem": self.filesystem,
            "Services": self.services,
            "NFS": self.nfs,
            "SMB": self.smb,
            "Directory Services": self.directoryservices,
            "Cyber Resilience": self.cyberresilience,
            "File Accelerator": self.fileaccelerator,
            "Advanced Global File Locking": self.agfl,
            "File IQ": self.nasuni_iq
        }
        
        return [name for name, status in components.items() if status == "Healthy"]
    
    @property
    def no_results_components(self) -> List[str]:
        """Get list of components with no monitoring results."""
        components = {
            "Network": self.network,
            "Memory": self.memory,
            "CPU": self.cpu,
            "Disk": self.disk,
            "Filesystem": self.filesystem,
            "Services": self.services,
            "NFS": self.nfs,
            "SMB": self.smb,
            "Directory Services": self.directoryservices,
            "Cyber Resilience": self.cyberresilience,
            "File Accelerator": self.fileaccelerator,
            "Advanced Global File Locking": self.agfl,
            "File IQ": self.nasuni_iq
        }
        
        return [name for name, status in components.items() if status == "No Results"]
    
    @property
    def health_score(self) -> float:
        """Calculate a health score (0-100) based on component status."""
        components = [
            self.network, self.memory, self.cpu, self.disk, 
            self.filesystem, self.services, self.nfs, self.smb,
            self.directoryservices, self.cyberresilience, 
            self.fileaccelerator, self.agfl, self.nasuni_iq
        ]
        
        # Only count components that have actual results
        scored_components = [
            comp for comp in components 
            if comp and comp not in ["", "No Results"]
        ]
        
        if not scored_components:
            return 0.0
        
        healthy_count = sum(1 for comp in scored_components if comp == "Healthy")
        return round((healthy_count / len(scored_components)) * 100, 1)
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get a summary dictionary with key information."""
        return {
            "filer_serial_number": self.filer_serial_number,
            "last_updated": self.last_updated,
            "overall_status": self.overall_health_status,
            "health_score": self.health_score,
            "is_healthy": self.is_healthy,
            "is_unhealthy": self.is_unhealthy,
            "has_warnings": self.has_warnings,
            "unhealthy_components": self.unhealthy_components,
            "healthy_components": self.healthy_components,
            "no_results_components": self.no_results_components,
            "total_components": len(self.healthy_components) + len(self.unhealthy_components),
            
            # Individual component statuses
            "network": self.network,
            "memory": self.memory,
            "cpu": self.cpu,
            "disk": self.disk,
            "filesystem": self.filesystem,
            "services": self.services,
            "nfs": self.nfs,
            "smb": self.smb,
            "directoryservices": self.directoryservices,
            "cyberresilience": self.cyberresilience,
            "fileaccelerator": self.fileaccelerator,
            "agfl": self.agfl,
            "nasuni_iq": self.nasuni_iq
        }