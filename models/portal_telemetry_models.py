#!/usr/bin/env python3
"""Data models for Portal snapshot timeline (protection) telemetry."""

from typing import Dict, Any, Optional, List
from datetime import datetime
from models.base import BaseModel


class SnapshotEvent(BaseModel):
    """Base model for snapshot phase events."""
    
    def _parse_data(self, data: Dict[str, Any]):
        """Parse snapshot event data."""
        self.phase = data.get("phase", "")  # "data_snapshot" or "metadata_snapshot"
        self.appliance = data.get("appliance", "")  # Appliance name/description
        self.serial_number = data.get("serial_number", "")  # Appliance serial number
        self.start_time = data.get("start_time", 0)  # Unix epoch milliseconds
        self.end_time = data.get("end_time", 0)  # Unix epoch milliseconds
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Duration of this phase in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) / 1000.0
        return None
    
    @property
    def start_datetime(self) -> Optional[datetime]:
        """Convert start time to datetime."""
        if self.start_time:
            try:
                return datetime.fromtimestamp(self.start_time / 1000.0)
            except:
                return None
        return None
    
    @property
    def end_datetime(self) -> Optional[datetime]:
        """Convert end time to datetime."""
        if self.end_time:
            try:
                return datetime.fromtimestamp(self.end_time / 1000.0)
            except:
                return None
        return None
    
    @property
    def start_time_str(self) -> str:
        """Get human-readable start time."""
        dt = self.start_datetime
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "Unknown"
    
    @property
    def end_time_str(self) -> str:
        """Get human-readable end time."""
        dt = self.end_datetime
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "Unknown"
    
    def format_duration(self, seconds: Optional[float]) -> str:
        """Format duration in a human-readable way."""
        if seconds is None:
            return "N/A"
        
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.2f}h"


class MetadataSnapshotEvent(SnapshotEvent):
    """Metadata snapshot event - creates the restore point."""
    
    def _parse_data(self, data: Dict[str, Any]):
        """Parse metadata snapshot event."""
        super()._parse_data(data)
        self.volume_version = data.get("volume_version", 0)  # Snapshot restore point version
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get summary dictionary."""
        return {
            "phase": self.phase,
            "appliance": self.appliance,
            "serial_number": self.serial_number,
            "volume_version": self.volume_version,
            "start_time": self.start_time_str,
            "end_time": self.end_time_str,
            "duration": self.format_duration(self.duration_seconds),
            "duration_seconds": self.duration_seconds
        }


class DataSnapshotEvent(SnapshotEvent):
    """Data snapshot event - protects data to cloud."""
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get summary dictionary."""
        return {
            "phase": self.phase,
            "appliance": self.appliance,
            "serial_number": self.serial_number,
            "start_time": self.start_time_str,
            "end_time": self.end_time_str,
            "duration": self.format_duration(self.duration_seconds),
            "duration_seconds": self.duration_seconds
        }


class SnapshotTimelineAnalysis:
    """Analysis of snapshot timeline events."""
    
    def __init__(
        self, 
        data_events: List[DataSnapshotEvent],
        metadata_events: List[MetadataSnapshotEvent],
        metadata: Dict[str, Any]
    ):
        self.data_events = data_events
        self.metadata_events = metadata_events
        self.appliance_count = metadata.get("appliance_count", 0)
        self.min_time = metadata.get("min_time", 0)
        self.max_time = metadata.get("max_time", 0)
    
    @property
    def latest_snapshot(self) -> Optional[MetadataSnapshotEvent]:
        """Get the latest snapshot (highest volume_version)."""
        if self.metadata_events:
            return max(self.metadata_events, key=lambda e: e.volume_version or 0)
        return None
    
    @property
    def latest_volume_version(self) -> Optional[int]:
        """Get the latest volume version."""
        if self.latest_snapshot:
            return self.latest_snapshot.volume_version
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Calculate comprehensive statistics from timeline events."""
        
        stats = {
            "appliance_count": self.appliance_count,
            "total_data_events": len(self.data_events),
            "total_metadata_events": len(self.metadata_events),
            "time_range": {
                "start": datetime.fromtimestamp(self.min_time / 1000.0).strftime("%Y-%m-%d %H:%M:%S") if self.min_time else "N/A",
                "end": datetime.fromtimestamp(self.max_time / 1000.0).strftime("%Y-%m-%d %H:%M:%S") if self.max_time else "N/A"
            }
        }
        
        # Latest snapshot info
        if self.latest_snapshot:
            stats["latest_snapshot"] = {
                "volume_version": self.latest_snapshot.volume_version,
                "appliance": self.latest_snapshot.appliance,
                "serial_number": self.latest_snapshot.serial_number,
                "completed_at": self.latest_snapshot.end_time_str,
                "duration": self.latest_snapshot.format_duration(self.latest_snapshot.duration_seconds)
            }
        
        # Data phase statistics
        if self.data_events:
            data_durations = [e.duration_seconds for e in self.data_events if e.duration_seconds is not None]
            
            if data_durations:
                longest_data = max(self.data_events, key=lambda e: e.duration_seconds or 0)
                
                stats["data_phase_statistics"] = {
                    "total_events": len(self.data_events),
                    "avg_duration_seconds": sum(data_durations) / len(data_durations),
                    "avg_duration": self._format_duration(sum(data_durations) / len(data_durations)),
                    "min_duration_seconds": min(data_durations),
                    "min_duration": self._format_duration(min(data_durations)),
                    "max_duration_seconds": max(data_durations),
                    "max_duration": self._format_duration(max(data_durations)),
                    "longest_on_appliance": longest_data.appliance,
                    "longest_serial": longest_data.serial_number
                }
        
        # Metadata phase statistics
        if self.metadata_events:
            metadata_durations = [e.duration_seconds for e in self.metadata_events if e.duration_seconds is not None]
            
            if metadata_durations:
                longest_metadata = max(self.metadata_events, key=lambda e: e.duration_seconds or 0)
                
                stats["metadata_phase_statistics"] = {
                    "total_events": len(self.metadata_events),
                    "avg_duration_seconds": sum(metadata_durations) / len(metadata_durations),
                    "avg_duration": self._format_duration(sum(metadata_durations) / len(metadata_durations)),
                    "min_duration_seconds": min(metadata_durations),
                    "min_duration": self._format_duration(min(metadata_durations)),
                    "max_duration_seconds": max(metadata_durations),
                    "max_duration": self._format_duration(max(metadata_durations)),
                    "longest_on_appliance": longest_metadata.appliance,
                    "longest_serial": longest_metadata.serial_number
                }
        
        # Per-appliance breakdown
        stats["by_appliance"] = {}
        
        # Group events by appliance
        appliances = set(e.appliance for e in self.data_events + self.metadata_events)
        
        for appliance in appliances:
            app_data_events = [e for e in self.data_events if e.appliance == appliance]
            app_metadata_events = [e for e in self.metadata_events if e.appliance == appliance]
            
            # Get serial number for this appliance
            serial = app_data_events[0].serial_number if app_data_events else (
                app_metadata_events[0].serial_number if app_metadata_events else "Unknown"
            )
            
            # Get latest version created by this appliance
            latest_version = None
            latest_time = None
            if app_metadata_events:
                latest_event = max(app_metadata_events, key=lambda e: e.volume_version or 0)
                latest_version = latest_event.volume_version
                latest_time = latest_event.end_time_str
            
            # Calculate average durations
            data_durations = [e.duration_seconds for e in app_data_events if e.duration_seconds]
            metadata_durations = [e.duration_seconds for e in app_metadata_events if e.duration_seconds]
            
            stats["by_appliance"][appliance] = {
                "serial_number": serial,
                "data_events": len(app_data_events),
                "metadata_events": len(app_metadata_events),
                "total_snapshots_created": len(app_metadata_events),
                "latest_version_created": latest_version,
                "latest_snapshot_time": latest_time,
                "avg_data_phase": self._format_duration(sum(data_durations) / len(data_durations)) if data_durations else "N/A",
                "avg_metadata_phase": self._format_duration(sum(metadata_durations) / len(metadata_durations)) if metadata_durations else "N/A"
            }
        
        # Most active appliance (by metadata events = actual snapshots created)
        if stats["by_appliance"]:
            most_active = max(
                stats["by_appliance"].items(),
                key=lambda x: x[1]["metadata_events"]
            )
            stats["most_active_appliance"] = {
                "name": most_active[0],
                "snapshots_created": most_active[1]["metadata_events"],
                "percentage": (most_active[1]["metadata_events"] / len(self.metadata_events) * 100) if self.metadata_events else 0
            }
        
        return stats
    
    def get_insights(self) -> List[str]:
        """Generate insights from snapshot timeline."""
        insights = []
        
        if not self.metadata_events:
            insights.append("⚠️ No metadata snapshot events found - no restore points created")
            return insights
        
        stats = self.get_statistics()
        
        # Latest snapshot
        if stats.get("latest_snapshot"):
            latest = stats["latest_snapshot"]
            insights.append(f"📌 Latest snapshot version {latest['volume_version']} created by {latest['appliance']} at {latest['completed_at']}")
        
        # Data phase performance
        if stats.get("data_phase_statistics"):
            data = stats["data_phase_statistics"]
            if data["max_duration_seconds"] > 30:  # Over 30 seconds
                insights.append(f"⏱️ Longest data protection phase: {data['max_duration']} on {data['longest_on_appliance']}")
            
            if data["avg_duration_seconds"] > 10:  # Over 10 seconds average
                insights.append(f"📊 Data phase averages {data['avg_duration']} - consider reviewing snapshot schedules")
        
        # Metadata phase performance
        if stats.get("metadata_phase_statistics"):
            meta = stats["metadata_phase_statistics"]
            if meta["max_duration_seconds"] > 15:  # Over 15 seconds
                insights.append(f"⏱️ Longest metadata phase: {meta['max_duration']} on {meta['longest_on_appliance']}")
        
        # Activity distribution
        if stats.get("most_active_appliance"):
            active = stats["most_active_appliance"]
            if active["percentage"] > 60:
                insights.append(f"📊 {active['name']} created {active['percentage']:.0f}% of snapshots ({active['snapshots_created']} versions)")
        
        # Appliance comparison
        if len(stats.get("by_appliance", {})) > 1:
            appliances = stats["by_appliance"]
            snapshot_counts = {k: v["metadata_events"] for k, v in appliances.items()}
            
            if max(snapshot_counts.values()) > min(snapshot_counts.values()) * 2:
                insights.append(f"⚖️ Uneven snapshot activity - some appliances creating 2x more snapshots than others")
        
        # Snapshot frequency
        if len(self.metadata_events) > 1:
            time_span_ms = self.max_time - self.min_time
            time_span_hours = time_span_ms / (1000 * 3600)
            frequency_hours = time_span_hours / len(self.metadata_events)
            
            insights.append(f"⏰ Snapshots created every {frequency_hours:.1f} hours on average")
        
        return insights
    
    def _format_duration(self, seconds: Optional[float]) -> str:
        """Format duration in a human-readable way."""
        if seconds is None:
            return "N/A"
        
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.2f}h"
