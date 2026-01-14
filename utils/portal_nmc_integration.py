#!/usr/bin/env python3
"""Integration helpers between NMC and Portal APIs."""

from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
from api.volumes_api import VolumesAPIClient
from api.filers_api import FilersAPIClient
from config.logging_setup import get_logger

if TYPE_CHECKING:
    from api.portal_volumes_api import PortalVolumesAPIClient
    from api.portal_edges_api import PortalEdgesAPIClient

logger = get_logger(__name__)


class NMCPortalIntegration:
    """Helper class to bridge NMC and Portal API data."""
    
    def __init__(
        self, 
        volumes_client: VolumesAPIClient, 
        filers_client: FilersAPIClient,
        portal_volumes_client: Optional["PortalVolumesAPIClient"] = None,
        portal_edges_client: Optional["PortalEdgesAPIClient"] = None,
    ):
        self.volumes_client = volumes_client
        self.filers_client = filers_client
        self.portal_volumes_client = portal_volumes_client
        self.portal_edges_client = portal_edges_client
        self._cached_filers: Optional[List[Dict[str, Any]]] = None
    
    async def get_volume_guid_by_name(self, volume_name: str) -> Optional[str]:
        """
        Get volume GUID from volume name using NMC API.
        
        Args:
            volume_name: Volume name to search for
            
        Returns:
            Volume GUID if found, None otherwise
        """
        logger.info(f"Looking up volume GUID for: {volume_name}")
        
        try:
            volumes = await self.volumes_client.get_volumes_as_models()
            
            for volume in volumes:
                if volume.name.lower() == volume_name.lower():
                    logger.info(f"Found volume GUID: {volume.guid}")
                    return volume.guid
            
            logger.warning(f"Volume not found: {volume_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error looking up volume: {e}")
            return None
    
    async def get_filer_serials_for_volume(self, volume_guid: str) -> List[str]:
        """
        Get all filer serial numbers connected to a volume.
        
        PRIORITY ORDER:
        1. Portal API (preferred) - get volume details with edge IDs, then lookup serials
        2. NMC volume-filer details API
        3. NMC volume data (master filer)
        4. NMC all filers (last resort)
        
        Args:
            volume_guid: Volume GUID
            
        Returns:
            List of appliance serial numbers (for Portal telemetry API calls)
        """
        logger.info(f"Getting filer serial numbers for volume: {volume_guid}")
        
        serial_numbers = []
        
        # ============================================================
        # PRIORITY 1: Portal API (preferred)
        # ============================================================
        if self.portal_volumes_client and self.portal_edges_client:
            try:
                logger.debug("Trying Portal API for volume serial lookup...")
                volume = await self.portal_volumes_client.get_volume(volume_guid)
                
                if volume and volume.edges:
                    edge_ids = []
                    
                    # Get master edge ID
                    if volume.edges.master and volume.edges.master.id:
                        edge_ids.append(volume.edges.master.id)
                        logger.debug(f"Portal: Found master edge ID: {volume.edges.master.id}")
                    
                    # Get connected edge IDs
                    if volume.edges.connected:
                        edge_ids.extend(volume.edges.connected)
                        logger.debug(f"Portal: Found {len(volume.edges.connected)} connected edge(s)")
                    
                    # Convert edge IDs to serial numbers
                    for edge_id in edge_ids:
                        try:
                            edge = await self.portal_edges_client.get_edge(edge_id)
                            if edge and edge.serial:
                                if edge.serial not in serial_numbers:
                                    serial_numbers.append(edge.serial)
                                    logger.debug(f"Portal: Added serial {edge.serial} for edge {edge.description}")
                        except Exception as e:
                            logger.warning(f"Portal: Could not get edge details for {edge_id}: {e}")
                    
                    if serial_numbers:
                        logger.info(f"Portal API: Found {len(serial_numbers)} filer serial(s)")
                        return serial_numbers
                else:
                    logger.debug("Portal: Volume has no edge information")
                    
            except Exception as e:
                logger.warning(f"Portal API lookup failed: {e}")
        else:
            logger.debug("Portal clients not available, skipping Portal lookup")
        
        # ============================================================
        # PRIORITY 2: NMC volume-filer details API
        # ============================================================
        try:
            from api.volume_filer_details_api import VolumeFilerDetailsAPIClient
            vfd_client = VolumeFilerDetailsAPIClient(self.volumes_client.config)
            
            logger.debug("Trying NMC volume-filer details API...")
            response = await vfd_client.get_volume_filer_details(volume_guid)
            
            if "error" not in response:
                # Get owner/master filer
                if response.get("owner") and response["owner"].get("exists"):
                    owner_serial = response["owner"].get("filer_serial")
                    if owner_serial and owner_serial not in serial_numbers:
                        serial_numbers.append(owner_serial)
                        logger.debug(f"NMC: Found owner filer: {owner_serial}")
                
                # Get remote connections
                if response.get("remote_connections"):
                    remote_filers = response["remote_connections"].get("filers", [])
                    for filer in remote_filers:
                        serial = filer.get("filer_serial")
                        if serial and serial not in serial_numbers:
                            serial_numbers.append(serial)
                            logger.debug(f"NMC: Added remote filer: {serial}")
                
                if serial_numbers:
                    logger.info(f"NMC volume-filer details: Found {len(serial_numbers)} filer serial(s)")
                    return serial_numbers
            else:
                logger.debug(f"NMC volume-filer details error: {response.get('error')}")
                
        except ImportError:
            logger.debug("NMC volume-filer details API not available")
        except Exception as e:
            logger.debug(f"NMC volume-filer details exception: {e}")
        
        # ============================================================
        # PRIORITY 3: NMC volume data (master filer)
        # ============================================================
        try:
            logger.debug("Trying NMC volume data for master filer...")
            volumes = await self.volumes_client.get_volumes_as_models()
            
            target_volume = None
            for volume in volumes:
                if volume.guid == volume_guid:
                    target_volume = volume
                    break
            
            if target_volume:
                logger.debug(f"NMC: Found volume: {target_volume.name}")
                if target_volume.master_filer_serial:
                    if target_volume.master_filer_serial not in serial_numbers:
                        serial_numbers.append(target_volume.master_filer_serial)
                        logger.info(f"NMC: Added master filer: {target_volume.master_filer_serial}")
                        return serial_numbers
            else:
                logger.debug(f"NMC: Volume not found: {volume_guid}")
                
        except Exception as e:
            logger.debug(f"NMC volume data exception: {e}")
        
        # ============================================================
        # PRIORITY 4: NMC all filers (last resort)
        # ============================================================
        if not serial_numbers:
            logger.warning("No serials found, falling back to all NMC filers...")
            try:
                filers_response = await self.filers_client.list_filers()
                
                if "items" in filers_response:
                    for filer_data in filers_response["items"]:
                        serial = filer_data.get("serial_number")
                        if serial:
                            serial_numbers.append(serial)
                    
                    if serial_numbers:
                        logger.info(f"NMC all filers: Returning {len(serial_numbers)} serial(s)")
                        return serial_numbers
                        
            except Exception as e:
                logger.error(f"NMC all filers exception: {e}")
        
        logger.error("No filer serials found for volume via any method")
        return []
    
    async def get_filer_guid_by_serial(self, filer_serial: str) -> Optional[str]:
        """
        Get filer GUID from serial number.
        
        Args:
            filer_serial: Filer serial number (e.g., "demoEdge1")
            
        Returns:
            Filer GUID if found, None otherwise
        """
        logger.info(f"Looking up filer GUID for serial: {filer_serial}")
        
        try:
            # Use the filers API directly to get GUID
            filers_response = await self.filers_client.list_filers()
            
            if "error" in filers_response:
                logger.error(f"Error fetching filers: {filers_response['error']}")
                return None
            
            for filer_data in filers_response.get("items", []):
                # Check both serial_number and description fields
                if (filer_data.get("serial_number") == filer_serial or 
                    filer_data.get("description") == filer_serial):
                    guid = filer_data.get("guid")
                    if guid:
                        logger.info(f"Found filer GUID: {filer_serial} -> {guid}")
                        return guid
            
            logger.warning(f"Filer not found: {filer_serial}")
            return None
            
        except Exception as e:
            logger.error(f"Error looking up filer GUID: {e}")
            return None

    async def resolve_filer_identifier(self, identifier: str) -> Tuple[Optional[str], str]:
        """Resolve filer identifier (serial, name/description, or edge ID) to a serial number.
        
        Uses Portal Edges API as the primary source for appliance resolution.
        
        Args:
            identifier: Edge serial number, description/name, or edge ID (UUID)
            
        Returns:
            Tuple of (serial_number, match_type) or (None, "not_found")
        """
        import re
        
        normalized = (identifier or "").strip()
        if not normalized:
            return None, "unknown"

        normalized_lower = normalized.lower()
        
        # Check if it looks like a UUID
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE
        )
        is_uuid = bool(uuid_pattern.match(normalized))

        # Use Portal Edges API to resolve
        if self.portal_edges_client:
            try:
                edges_response = await self.portal_edges_client.get_edges()
                for edge in edges_response.items:
                    edge_serial = (edge.serial or "").strip()
                    edge_desc = (edge.description or "").strip()
                    edge_id = (edge.id or "").strip()
                    
                    if not edge_serial:
                        continue
                    
                    # Match by serial number
                    if edge_serial.lower() == normalized_lower:
                        logger.info(f"Resolved via Portal: serial match {edge_serial}")
                        return edge_serial, "serial"
                    # Match by description/name
                    if edge_desc and edge_desc.lower() == normalized_lower:
                        logger.info(f"Resolved via Portal: {edge_desc} -> {edge_serial}")
                        return edge_serial, "description"
                    # Match by edge ID
                    if edge_id and edge_id.lower() == normalized_lower:
                        logger.info(f"Resolved via Portal: edge ID {edge_id} -> {edge_serial}")
                        return edge_serial, "edge_id"
            except Exception as e:
                logger.error(f"Portal edges lookup failed: {e}")

        # If it's already a valid UUID and Portal lookup failed/unavailable, use it directly
        # (it might be a serial number that just wasn't in the list)
        if is_uuid:
            logger.info(f"Using provided UUID directly: {normalized}")
            return normalized, "uuid_provided"
        
        # Not a UUID and not found in Portal - can't resolve
        logger.error(f"Filer identifier '{identifier}' not found in Portal and is not a valid UUID")
        return None, "not_found"

    async def resolve_filer_to_guid(self, identifier: str) -> Tuple[Optional[str], str]:
        """Resolve filer identifier (serial, name, or GUID) to a filer GUID.
        
        This is needed for Portal Edge API which uses filer GUID for lookups.
        Uses Portal Edges API as PRIMARY source (not NMC).
        
        Args:
            identifier: Filer serial number, description/name, or GUID
            
        Returns:
            Tuple of (filer_guid, match_type) where match_type indicates how it was resolved
        """
        import re
        
        normalized = (identifier or "").strip()
        if not normalized:
            return None, "unknown"

        normalized_lower = normalized.lower()
        
        # Check if it looks like a UUID (GUID format)
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE
        )
        is_uuid = bool(uuid_pattern.match(normalized))

        # Use Portal Edges API as PRIMARY source (not NMC)
        if hasattr(self, 'portal_edges_client') and self.portal_edges_client:
            try:
                edges_response = await self.portal_edges_client.get_edges()
                if edges_response and hasattr(edges_response, 'items') and edges_response.items:
                    for edge in edges_response.items:
                        edge_id = (edge.id or "").strip()
                        edge_description = (edge.description or "").strip()
                        edge_serial = (edge.serial or "").strip()
                        
                        # Edge id is the GUID we need
                        if not edge_id:
                            continue
                        
                        if edge_id.lower() == normalized_lower:
                            logger.info(f"Portal: Resolved edge id as GUID directly: {edge_id}")
                            return edge_id, "guid"
                        if edge_serial and edge_serial.lower() == normalized_lower:
                            logger.info(f"Portal: Resolved edge serial to GUID: {edge_serial} -> {edge_id}")
                            return edge_id, "serial"
                        if edge_description and edge_description.lower() == normalized_lower:
                            logger.info(f"Portal: Resolved edge description to GUID: {edge_description} -> {edge_id}")
                            return edge_id, "description"
            except Exception as exc:
                logger.warning(f"Portal Edges API lookup failed, cannot resolve: {exc}")

        # Not found in Portal - if it looks like a UUID, use it directly
        if is_uuid:
            logger.info(f"Using provided UUID directly (not found in Portal): {normalized}")
            return normalized, "uuid_direct"
        
        # Not a UUID and not in Portal - can't resolve
        logger.warning(f"Filer identifier '{identifier}' not found in Portal and is not a valid UUID")
        return None, "not_found"

    async def _get_cached_filers(self) -> List[Dict[str, Any]]:
        """Return cached filer list, fetching from NMC if necessary."""
        if self._cached_filers is not None:
            return self._cached_filers

        try:
            response = await self.filers_client.list_filers()
        except Exception as exc:
            logger.error(f"Failed to fetch filers for cache: {exc}")
            self._cached_filers = []
            return self._cached_filers

        if "error" in response:
            logger.error(f"Filer list error: {response['error']}")
            self._cached_filers = []
        else:
            self._cached_filers = response.get("items", [])
            logger.info(f"Cached {len(self._cached_filers)} filer records for lookup")

        return self._cached_filers
    
    async def resolve_volume_identifier(self, identifier: str) -> Tuple[Optional[str], str]:
        """
        Resolve a volume identifier (name or GUID) to GUID.
        
        Args:
            identifier: Volume name or GUID
            
        Returns:
            Tuple of (volume_guid, identifier_type)
            identifier_type: "guid" or "name"
        """
        # Check if it looks like a GUID (contains hyphens and underscores)
        if "-" in identifier and "_" in identifier:
            logger.debug(f"Identifier looks like GUID: {identifier}")
            return identifier, "guid"
        
        # Otherwise, treat as name and look up
        logger.debug(f"Treating as volume name: {identifier}")
        guid = await self.get_volume_guid_by_name(identifier)
        return guid, "name"