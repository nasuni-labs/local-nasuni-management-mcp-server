#!/usr/bin/env python3
"""Optimized configuration management for the MCP server."""

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
        """Get API token from environment or file - called only once."""
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