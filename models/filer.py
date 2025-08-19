#!/usr/bin/env python3
"""Filer-related data models."""

from typing import Dict, Any, List
from models.base import BaseModel, NestedModel


class AlertThresholds(NestedModel):
    """Alert threshold settings."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.snapshot_alert_settings = data.get("snapshot_alert_settings", {})


class AutoUpdate(NestedModel):
    """Auto-update settings."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.hour = data.get("hour", 0)
        self.days = {
            day: data.get(day, False) 
            for day in ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
        }


class CacheReserved(NestedModel):
    """Cache reservation settings."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.reserved = data.get("reserved", "unset")
        self.maxv = data.get("maxv", 90)
        self.minv = data.get("minv", 5)


class NetworkSettings(NestedModel):
    """Network configuration settings."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.hostname = data.get("hostname", "")
        self.default_gateway = data.get("default_gateway", "")
        self.ip_addresses = data.get("ip_addresses", [])
        self.dns_servers = data.get("dns_servers", [])
        self.search_domains = data.get("search_domains", [])


class CacheStatus(NestedModel):
    """Cache status information."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.size = data.get("size", 0)
        self.used = data.get("used", 0)
        self.dirty = data.get("dirty", 0)
        self.free = data.get("free", 0)
        self.percent_used = data.get("percent_used", 0.0)
    
    @property
    def size_gb(self) -> float:
        """Cache size in GB."""
        return round(self.size / (1024**3), 2)
    
    @property
    def used_gb(self) -> float:
        """Cache used in GB."""
        return round(self.used / (1024**3), 2)


class Platform(NestedModel):
    """Platform information."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.platform_name = data.get("platform_name", "")
        self.cache_status = CacheStatus(data.get("cache_status", {}))
        self.cpu = data.get("cpu", {})
        self.memory = data.get("memory", "0")
    
    @property
    def cpu_cores(self) -> int:
        """Number of CPU cores."""
        return self.cpu.get("cores", 0)
    
    @property
    def cpu_model(self) -> str:
        """CPU model name."""
        return self.cpu.get("model", "Unknown")


class Status(NestedModel):
    """Filer status information."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.offline = data.get("offline", False)
        self.osversion = data.get("osversion", "")
        self.platform = Platform(data.get("platform", {}))
        self.updates = data.get("updates", {})
        self.uptime = data.get("uptime", 0)
    
    @property
    def is_online(self) -> bool:
        """Whether the filer is online."""
        return not self.offline
    
    @property
    def uptime_days(self) -> int:
        """Uptime in days."""
        return self.uptime // 86400
    
    @property
    def current_version(self) -> str:
        """Current software version."""
        return self.updates.get("current_version", "Unknown")


class Settings(NestedModel):
    """Filer settings."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.alert_thresholds = AlertThresholds(data.get("alert_thresholds", {}))
        self.autoupdate = AutoUpdate(data.get("autoupdate", {}))
        self.cache_reserved = CacheReserved(data.get("cache_reserved", {}))
        self.cifs = data.get("cifs", {})
        self.ftp = data.get("ftp", {})
        self.network_settings = NetworkSettings(data.get("network_settings", {}))
        self.qos = data.get("qos", {})
        self.remote_support = data.get("remote_support", {})
        self.snmp = data.get("snmp", {})
        self.time = data.get("time", {})
    
    @property
    def timezone(self) -> str:
        """System timezone."""
        return self.time.get("timezone", "Unknown")


class Filer(BaseModel):
    """Main filer model."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.build = data.get("build", "")
        self.description = data.get("description", "")
        self.guid = data.get("guid", "")
        self.management_state = data.get("management_state", "")
        self.serial_number = data.get("serial_number", "")
        self.settings = Settings(data.get("settings", {}))
        self.status = Status(data.get("status", {}))
        self.links = data.get("links", {})
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get a summary dictionary with key information."""
        return {
            "description": self.description,
            "build": self.build,
            "guid": self.guid,
            "serial_number": self.serial_number,
            "management_state": self.management_state,
            "hostname": self.settings.network_settings.hostname,
            "ip_addresses": self.settings.network_settings.ip_addresses,
            "platform": self.status.platform.platform_name,
            "uptime": self.status.uptime,
            "uptime_days": self.status.uptime_days,
            "cache_used_percent": self.status.platform.cache_status.percent_used,
            "cache_size_gb": self.status.platform.cache_status.size_gb,
            "cache_used_gb": self.status.platform.cache_status.used_gb,
            "offline": self.status.offline,
            "online": self.status.is_online,
            "osversion": self.status.osversion,
            "current_version": self.status.current_version,
            "memory_mb": self.status.platform.memory,
            "cpu_cores": self.status.platform.cpu_cores,
            "cpu_model": self.status.platform.cpu_model,
            "timezone": self.settings.timezone,
        }