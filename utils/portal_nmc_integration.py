#!/usr/bin/env python3
"""Integration helpers between NMC and Portal APIs."""

from typing import Dict, Any, List, Optional, Tuple
from api.volumes_api import VolumesAPIClient
from api.filers_api import FilersAPIClient
from config.logging_setup import get_logger

logger = get_logger(__name__)


class NMCPortalIntegration:
    """Helper class to bridge NMC and Portal API data."""
    
    def __init__(self, volumes_client: VolumesAPIClient, filers_client: FilersAPIClient):
        self.volumes_client = volumes_client
        self.filers_client = filers_client
    
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
        Get all filer serial numbers connected to a volume using NMC API.
        
        Args:
            volume_guid: Volume GUID
            
        Returns:
            List of appliance serial numbers (for Portal API calls)
        """
        logger.info(f"Getting filer serial numbers for volume: {volume_guid}")
        
        serial_numbers = []
        
        try:
            # Try volume-filer details API first (most comprehensive)
            try:
                from api.volume_filer_details_api import VolumeFilerDetailsAPIClient
                vfd_client = VolumeFilerDetailsAPIClient(self.volumes_client.config)
                
                logger.debug("Fetching volume-filer details...")
                response = await vfd_client.get_volume_filer_details(volume_guid)
                
                if "error" in response:
                    logger.warning(f"Volume-filer details error: {response['error']}")
                else:
                    # Parse the new structure with owner and remote_connections
                    logger.debug(f"Volume-filer response keys: {response.keys()}")
                    
                    # Get owner/master filer
                    if response.get("owner") and response["owner"].get("exists"):
                        owner_serial = response["owner"].get("filer_serial")
                        if owner_serial:
                            serial_numbers.append(owner_serial)
                            logger.info(f"Found owner filer: {owner_serial}")
                    
                    # Get remote connections
                    if response.get("remote_connections"):
                        remote_filers = response["remote_connections"].get("filers", [])
                        logger.info(f"Found {len(remote_filers)} remote connection(s)")
                        
                        for filer in remote_filers:
                            serial = filer.get("filer_serial")
                            if serial and serial not in serial_numbers:
                                serial_numbers.append(serial)
                                logger.debug(f"Added remote filer: {serial}")
                    
                    if serial_numbers:
                        logger.info(f"Successfully found {len(serial_numbers)} filer serial(s) via volume-filer details")
                        return serial_numbers
                    
            except ImportError as e:
                logger.debug(f"Volume-filer details API not available: {e}")
            except Exception as e:
                logger.warning(f"Volume-filer details exception: {e}")
                import traceback
                traceback.print_exc()
            
            # Fallback 1: Get from volume's master filer
            logger.debug("Fallback: Getting volume data from NMC...")
            volumes = await self.volumes_client.get_volumes_as_models()
            
            target_volume = None
            for volume in volumes:
                if volume.guid == volume_guid:
                    target_volume = volume
                    break
            
            if not target_volume:
                logger.warning(f"Volume not found in NMC: {volume_guid}")
                return []
            
            logger.info(f"Found volume: {target_volume.name}")
            
            # Get master filer serial
            if target_volume.master_filer_serial:
                if target_volume.master_filer_serial not in serial_numbers:
                    serial_numbers.append(target_volume.master_filer_serial)
                    logger.info(f"Added master filer: {target_volume.master_filer_serial}")
            
            # Fallback 2: Get all filers as last resort
            if not serial_numbers:
                logger.warning("No serials found via volume data, fetching all filers...")
                try:
                    filers_response = await self.filers_client.list_filers()
                    
                    if "items" in filers_response:
                        logger.info(f"Found {len(filers_response['items'])} total filers, adding all")
                        
                        for filer_data in filers_response["items"]:
                            serial = filer_data.get("serial_number")
                            if serial:
                                serial_numbers.append(serial)
                                logger.debug(f"Added filer: {serial}")
                        
                except Exception as e:
                    logger.error(f"Could not get all filers: {e}")
            
            if serial_numbers:
                logger.info(f"Returning {len(serial_numbers)} filer serial(s) via fallback")
                return serial_numbers
            else:
                logger.error("No filer serials found for volume")
                return []
            
        except Exception as e:
            logger.error(f"Error getting filer serials: {e}")
            import traceback
            traceback.print_exc()
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