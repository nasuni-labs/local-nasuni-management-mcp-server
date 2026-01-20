#!/usr/bin/env python3
"""Optimized configuration management for the MCP server with Portal support."""

import os
from typing import Any, Optional, Dict
from dataclasses import dataclass
from dotenv import load_dotenv
from config.server_instructions import server_instructions


# Load environment variables from .env file
load_dotenv()


@dataclass
class APIConfig:
    """Configuration for API connections."""
    base_url: str
    token: Optional[str] = None
    verify_ssl: bool = False
    timeout: float = 30.0


@dataclass
class PortalAPIConfig:
    """Configuration for Portal API connections."""
    base_url: str
    service_key: Optional[str] = None
    service_secret: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    verify_ssl: bool = True
    timeout: float = 30.0


class ConfigManager:
    """Configuration manager with support for both NMC and Portal APIs."""
    
    def __init__(self):
        # Load NMC configuration (required)
        self.api_config = self._load_api_config()
        
        # All NMC services use the same configuration
        self.filers_config = self.api_config
        self.shares_config = self.api_config 
        self.volumes_config = self.api_config
        
        # Load Portal configuration (optional)
        self.portal_config = self._load_portal_config()
        self.portal_enabled = self._is_portal_enabled()
        
        # Server instructions and behavior settings
        self.server_instructions = server_instructions
        self.behavior_settings = self._load_behavior_settings()
    
    def _load_api_config(self) -> APIConfig:
        """Load NMC API configuration once for all services."""
        base_url = os.getenv("API_BASE_URL", os.getenv("FILERS_API_URL", "https://3.18.196.153"))
        token = self._get_api_token()
        verify_ssl = os.getenv("VERIFY_SSL", "false").lower() == "true"
        timeout = float(os.getenv("API_TIMEOUT", "30.0"))
        
        return APIConfig(
            base_url=base_url,
            token=token,
            verify_ssl=verify_ssl,
            timeout=timeout
        )
    
    def _get_api_token(self) -> Optional[str]:
        """Get NMC API token from environment or file - called only once."""
        # Try environment variable first
        token = os.getenv("API_TOKEN", os.getenv("FILERS_API_TOKEN"))
        if token:
            return token
        
        # Try reading from file
        token_file = os.getenv("API_TOKEN_FILE", os.getenv("FILERS_TOKEN_FILE", "/path/to/your/token.txt"))
        try:
            with open(token_file, 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            print(f"Token file not found: {token_file}")
            return None
        except Exception as e:
            print(f"Error reading token file: {e}")
            return None
    
    def _load_portal_config(self) -> PortalAPIConfig:
        """Load Portal API configuration (optional)."""
        base_url = os.getenv("PORTAL_API_BASE_URL", "https://am1.portal.api.nasuni.com")
        service_key = os.getenv("PORTAL_SERVICE_KEY")
        service_secret = os.getenv("PORTAL_SERVICE_SECRET")
        access_token = os.getenv("PORTAL_ACCESS_TOKEN")
        refresh_token = os.getenv("PORTAL_REFRESH_TOKEN")
        verify_ssl = os.getenv("PORTAL_VERIFY_SSL", "true").lower() == "true"
        timeout = float(os.getenv("PORTAL_API_TIMEOUT", "30.0"))
        
        return PortalAPIConfig(
            base_url=base_url,
            service_key=service_key,
            service_secret=service_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            verify_ssl=verify_ssl,
            timeout=timeout
        )
    
    def _is_portal_enabled(self) -> bool:
        """Check if Portal integration is enabled (has required credentials)."""
        cfg = self.portal_config
        has_service_credentials = bool(cfg.service_key and cfg.service_secret)
        has_tokens = bool(cfg.access_token or cfg.refresh_token)
        return has_service_credentials or has_tokens
    
    def add_api_config(self, name: str) -> APIConfig:
        """Add configuration for a new API - reuses the same config."""
        setattr(self, f"{name}_config", self.api_config)
        return self.api_config
    
    def get_config_summary(self) -> Dict[str, str]:
        """Get configuration summary for debugging."""
        summary = {
            'nmc_base_url': self.api_config.base_url,
            'nmc_token_present': bool(self.api_config.token),
            'nmc_verify_ssl': self.api_config.verify_ssl,
            'nmc_timeout': self.api_config.timeout,
            'services': 'All NMC services use same config',
        }
        
        # Add Portal info if enabled
        if self.portal_enabled:
            summary.update({
                'portal_enabled': True,
                'portal_base_url': self.portal_config.base_url,
                'portal_service_key_present': bool(self.portal_config.service_key),
                'portal_service_secret_present': bool(self.portal_config.service_secret),
                'portal_access_token_present': bool(self.portal_config.access_token),
                'portal_verify_ssl': self.portal_config.verify_ssl,
            })
        else:
            summary['portal_enabled'] = False
            summary['portal_note'] = 'Portal credentials not configured (optional)'
        
        return summary
    
    def _load_behavior_settings(self) -> Dict[str, Any]:
        """Load behavioral configuration settings."""
        return {
            'auto_include_master_info': os.getenv('AUTO_INCLUDE_MASTER', 'true').lower() == 'true',
            'comprehensive_volume_reporting': os.getenv('COMPREHENSIVE_VOLUMES', 'true').lower() == 'true',
            'proactive_health_monitoring': os.getenv('PROACTIVE_HEALTH', 'true').lower() == 'true',
            'security_focus_enabled': os.getenv('SECURITY_FOCUS', 'true').lower() == 'true'
        }


# Global configuration instance
config = ConfigManager()