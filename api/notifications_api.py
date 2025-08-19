#!/usr/bin/env python3
"""Notifications API client implementation with backend filtering."""

import sys
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from api.base_client import BaseAPIClient
from models.notification import Notification


class NotificationsAPIClient(BaseAPIClient):
    """Client for interacting with the Notifications API."""
    
    async def list_notifications(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """
        Fetch notifications from the API.
        Note: The API only supports limit and offset parameters.
        All other filtering must be done on the client side.
        """
        print(f"Fetching notifications (limit={limit}, offset={offset})...", file=sys.stderr)
        
        # API only supports limit and offset
        response = await self.get(f"/api/v1.2/notifications/?limit={limit}&offset={offset}")
        
        if "error" not in response:
            items_count = len(response.get("items", []))
            total = response.get("total", 0)
            print(f"Successfully retrieved {items_count} notifications (total: {total})", file=sys.stderr)
        
        return response
    
    async def get_notification(self, notification_id: int) -> Dict[str, Any]:
        """Get a specific notification by ID."""
        print(f"Fetching notification {notification_id}...", file=sys.stderr)
        return await self.get(f"/api/v1.2/notifications/{notification_id}/")
    
    async def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            response = await self.get("/api/v1.2/notifications/?limit=1&offset=0")
            return "error" not in response
        except Exception:
            return False
    
    async def get_all_notifications_raw(self, max_items: int = 1000) -> List[Dict[str, Any]]:
        """
        Get raw notification data up to max_items (paginated).
        Returns raw dictionaries for maximum flexibility in filtering.
        """
        all_notifications = []
        offset = 0
        limit = 50  # API limit per request
        
        while len(all_notifications) < max_items:
            response = await self.list_notifications(limit=limit, offset=offset)
            
            if "error" in response:
                print(f"Error fetching notifications: {response['error']}", file=sys.stderr)
                break
            
            items = response.get("items", [])
            if not items:
                break  # No more items
            
            all_notifications.extend(items)
            
            # Check if we have more pages
            if not response.get("next"):
                break
            
            offset += limit
            
            # Stop if we've reached our max
            if len(all_notifications) >= max_items:
                all_notifications = all_notifications[:max_items]
                break
        
        print(f"Retrieved {len(all_notifications)} total notifications", file=sys.stderr)
        return all_notifications
    
    async def get_all_notifications(self, max_items: int = 500) -> List[Notification]:
        """
        Get all notifications up to max_items as Notification objects.
        This method is for backward compatibility.
        """
        raw_notifications = await self.get_all_notifications_raw(max_items=max_items)
        
        notifications = []
        for item in raw_notifications:
            try:
                notification = Notification(item)
                notifications.append(notification)
            except Exception as e:
                print(f"Error parsing notification: {e}", file=sys.stderr)
                continue
        
        return notifications
    
    async def get_notifications_by_origin(self, origin: str, limit: int = 100) -> List[Notification]:
        """Get notifications from a specific origin (filer)."""
        return await self.get_notifications_filtered(max_items=limit, origin=origin)
    
    async def get_notifications_by_priority(self, priority: str, limit: int = 100) -> List[Notification]:
        """Get notifications by priority level."""
        return await self.get_notifications_filtered(max_items=limit, priority=priority)
    
    async def get_notifications_by_name(self, name: str, limit: int = 100) -> List[Notification]:
        """Get notifications by name/type."""
        return await self.get_notifications_filtered(max_items=limit, name=name)
    
    async def get_notifications_by_volume(self, volume_name: str, limit: int = 100) -> List[Notification]:
        """Get notifications related to a specific volume."""
        return await self.get_notifications_filtered(max_items=limit, volume=volume_name)
    
    async def get_unacknowledged_notifications(self, limit: int = 100) -> List[Notification]:
        """Get unacknowledged notifications."""
        return await self.get_notifications_filtered(max_items=limit, acknowledged=False)
    
    async def get_urgent_notifications(self, limit: int = 100) -> List[Notification]:
        """Get urgent notifications."""
        return await self.get_notifications_filtered(max_items=limit, urgent=True)
    
    async def get_recent_notifications(self, hours: int = 24, limit: int = 200) -> List[Notification]:
        """Get notifications from the last N hours."""
        return await self.get_notifications_filtered(max_items=limit, hours=hours)
    
    async def get_notifications_filtered(
        self,
        max_items: int = 1000,
        origin: Optional[str] = None,
        priority: Optional[str] = None,
        name: Optional[str] = None,
        message_contains: Optional[str] = None,
        volume: Optional[str] = None,
        hours: Optional[int] = None,
        acknowledged: Optional[bool] = None,
        urgent: Optional[bool] = None
    ) -> List[Notification]:
        """
        Get notifications with client-side filtering.
        Since the API only supports limit/offset, we fetch notifications
        and filter them locally.
        """
        # Get raw notifications
        raw_notifications = await self.get_all_notifications_raw(max_items=max_items)
        
        # Convert to models
        notifications = []
        for item in raw_notifications:
            try:
                notification = Notification(item)
                notifications.append(notification)
            except Exception as e:
                print(f"Error parsing notification: {e}", file=sys.stderr)
                continue
        
        print(f"Parsed {len(notifications)} notifications, applying filters...", file=sys.stderr)
        
        # Apply filters
        filtered = notifications
        
        # Filter by origin
        if origin:
            filtered = [n for n in filtered if origin.lower() in n.origin.lower()]
            print(f"After origin filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by priority
        if priority:
            filtered = [n for n in filtered if n.priority.lower() == priority.lower()]
            print(f"After priority filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by name
        if name:
            filtered = [n for n in filtered if name.upper() in n.name.upper()]
            print(f"After name filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by message content
        if message_contains:
            filtered = [n for n in filtered if message_contains.lower() in n.message.lower()]
            print(f"After message filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by volume
        if volume:
            filtered = [n for n in filtered if n.volume_name and volume.lower() in n.volume_name.lower()]
            print(f"After volume filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by time
        if hours:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            time_filtered = []
            for n in filtered:
                if n.datetime_obj:
                    # Handle timezone-aware datetime
                    n_time = n.datetime_obj.replace(tzinfo=None) if n.datetime_obj.tzinfo else n.datetime_obj
                    if n_time > cutoff_time:
                        time_filtered.append(n)
            filtered = time_filtered
            print(f"After time filter ({hours} hours): {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by acknowledged status
        if acknowledged is not None:
            filtered = [n for n in filtered if n.acknowledged == acknowledged]
            print(f"After acknowledged filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by urgent status
        if urgent is not None:
            filtered = [n for n in filtered if n.urgent == urgent]
            print(f"After urgent filter: {len(filtered)} notifications", file=sys.stderr)
        
        print(f"Final filtered result: {len(filtered)} notifications", file=sys.stderr)
        return filtered
    
    async def search_notifications(
        self,
        search_terms: List[str],
        max_items: int = 1000,
        hours: Optional[int] = None
    ) -> List[Notification]:
        """
        Search notifications for any of the given terms in name or message.
        Useful for finding snapshot-related notifications.
        """
        raw_notifications = await self.get_all_notifications_raw(max_items=max_items)
        
        # Convert to models
        notifications = []
        for item in raw_notifications:
            try:
                notification = Notification(item)
                notifications.append(notification)
            except Exception as e:
                continue
        
        # Apply time filter if specified
        if hours:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            time_filtered = []
            for n in notifications:
                if n.datetime_obj:
                    n_time = n.datetime_obj.replace(tzinfo=None) if n.datetime_obj.tzinfo else n.datetime_obj
                    if n_time > cutoff_time:
                        time_filtered.append(n)
            notifications = time_filtered
        
        # Search for terms
        results = []
        for notif in notifications:
            for term in search_terms:
                term_lower = term.lower()
                if (term_lower in notif.name.lower() or 
                    term_lower in notif.message.lower()):
                    results.append(notif)
                    break  # Don't add the same notification multiple times
        
        print(f"Found {len(results)} notifications matching search terms", file=sys.stderr)
        return results
    
    async def get_notification_statistics(self, max_items: int = 1000) -> Dict[str, Any]:
        """
        Get statistics about notifications.
        Note: This method takes max_items as a parameter, not limit.
        """
        notifications = await self.get_notifications_filtered(max_items=max_items)
        
        if not notifications:
            return {
                "total": 0,
                "error": "No notifications found or API error"
            }
        
        # Collect statistics
        stats = {
            "total": len(notifications),
            "by_priority": {},
            "by_origin": {},
            "by_type": {},
            "by_name": {},
            "by_group": {},
            "acknowledged": 0,
            "unacknowledged": 0,
            "urgent": 0,
            "volume_related": 0,
            "snapshot_related": 0,
            "top_messages": {},
            "recent_1h": 0,
            "recent_24h": 0
        }
        
        # Snapshot-related terms
        snapshot_terms = ['snapshot', 'push', 'pull', 'sync', 'backup', 'restore']
        
        # Time calculations
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(hours=24)
        
        for notif in notifications:
            # Priority distribution
            priority = notif.priority
            stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1
            
            # Origin distribution
            origin = notif.origin or "Unknown"
            stats["by_origin"][origin] = stats["by_origin"].get(origin, 0) + 1
            
            # Type distribution
            notif_type = notif.notification_type
            stats["by_type"][notif_type] = stats["by_type"].get(notif_type, 0) + 1
            
            # Name distribution
            stats["by_name"][notif.name] = stats["by_name"].get(notif.name, 0) + 1
            
            # Group distribution
            group = notif.group
            stats["by_group"][group] = stats["by_group"].get(group, 0) + 1
            
            # Acknowledgment status
            if notif.acknowledged:
                stats["acknowledged"] += 1
            else:
                stats["unacknowledged"] += 1
            
            # Urgent status
            if notif.urgent:
                stats["urgent"] += 1
            
            # Volume related
            if notif.volume_name:
                stats["volume_related"] += 1
            
            # Snapshot related
            msg_lower = notif.message.lower()
            name_lower = notif.name.lower()
            if any(term in msg_lower or term in name_lower for term in snapshot_terms):
                stats["snapshot_related"] += 1
            
            # Message frequency
            msg_key = notif.name
            stats["top_messages"][msg_key] = stats["top_messages"].get(msg_key, 0) + 1
            
            # Recent notifications
            if notif.datetime_obj:
                dt = notif.datetime_obj.replace(tzinfo=None) if notif.datetime_obj.tzinfo else notif.datetime_obj
                if dt > one_hour_ago:
                    stats["recent_1h"] += 1
                if dt > one_day_ago:
                    stats["recent_24h"] += 1
        
        # Sort top messages
        stats["top_messages"] = dict(sorted(
            stats["top_messages"].items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10])
        
        # Sort by_name for most common notification types
        stats["by_name"] = dict(sorted(
            stats["by_name"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:20])
        
        return stats