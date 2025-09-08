#!/usr/bin/env python3
"""Optimized configuration management for the MCP server."""

import os
import sys
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


class ConfigManager:
    """Simplified configuration manager - one config for all services."""
    
    def __init__(self):
        # Load configuration once and reuse for all services
        self.api_config = self._load_api_config()
        
        # All services use the same configuration
        self.filers_config = self.api_config
        self.shares_config = self.api_config 
        self.volumes_config = self.api_config
        self.server_instructions = server_instructions
        self.behavior_settings = self._load_behavior_settings()
    
    def _load_api_config(self) -> APIConfig:
        """Load API configuration once for all services."""
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
        """Get API token from environment or file."""
        # Try environment variable first (includes .env file via dotenv)
        token = os.getenv("API_TOKEN") or os.getenv("FILERS_API_TOKEN")
        
        if token:
            # Also check if token is expired
            expires = os.getenv("API_TOKEN_EXPIRES") or os.getenv("FILERS_TOKEN_EXPIRES")
            if expires:
                try:
                    from datetime import datetime, timedelta
                    expires_clean = expires.replace("UTC", "+00:00")
                    expires_time = datetime.fromisoformat(expires_clean)
                    now = datetime.now(expires_time.tzinfo)
                    
                    if expires_time > now + timedelta(minutes=10):
                        # Token is still valid
                        return token
                    else:
                        print(f"Token expired, will need refresh", file=sys.stderr)
                        return None
                except:
                    pass
            return token
        
        return None
    
    def add_api_config(self, name: str) -> APIConfig:
        """Add configuration for a new API - reuses the same config."""
        setattr(self, f"{name}_config", self.api_config)
        return self.api_config
    
    def get_config_summary(self) -> Dict[str, str]:
        """Get configuration summary for debugging."""
        return {
            'base_url': self.api_config.base_url,
            'token_present': bool(self.api_config.token),
            'verify_ssl': self.api_config.verify_ssl,
            'timeout': self.api_config.timeout,
            'services': 'All services use same config'
        }
    
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