#!/usr/bin/env python3
"""Cloud credential data models."""

from typing import Dict, Any
from models.base import BaseModel


class CloudCredential(BaseModel):
    """Cloud credential model."""
    
    def _parse_data(self, data: Dict[str, Any]):
        self.cred_uuid = data.get("cred_uuid", "")
        self.name = data.get("name", "")
        self.filer_serial_number = data.get("filer_serial_number", "")
        self.cloud_provider = data.get("cloud_provider", "")
        self.account = data.get("account", "")
        self.hostname = data.get("hostname", "")
        self.status = data.get("status", "")
        self.secret = data.get("secret", "")
        self.note = data.get("note", "")
        self.in_use = data.get("in_use", False)
        self.skip_validation = data.get("skip_validation", False)
        self.links = data.get("links", {})
    
    @property
    def is_synced(self) -> bool:
        """Check if credential is synced."""
        return self.status.lower() == "synced"
    
    @property
    def is_aws(self) -> bool:
        """Check if this is an AWS credential."""
        return "s3" in self.cloud_provider.lower() or "aws" in self.cloud_provider.lower()
    
    @property
    def is_azure(self) -> bool:
        """Check if this is an Azure credential."""
        return "azure" in self.cloud_provider.lower()
    
    @property
    def is_gcp(self) -> bool:
        """Check if this is a Google Cloud credential."""
        return "google" in self.cloud_provider.lower() or "gcp" in self.cloud_provider.lower()
    
    @property
    def masked_account(self) -> str:
        """Get masked account identifier."""
        if len(self.account) > 8:
            return f"{self.account[:4]}...{self.account[-4:]}"
        return self.account
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get a summary dictionary with key information."""
        return {
            "cred_uuid": self.cred_uuid,
            "name": self.name,
            "filer_serial_number": self.filer_serial_number,
            "cloud_provider": self.cloud_provider,
            "account": self.account,
            "masked_account": self.masked_account,
            "hostname": self.hostname,
            "status": self.status,
            "is_synced": self.is_synced,
            "in_use": self.in_use,
            "note": self.note,
            "skip_validation": self.skip_validation,
            "is_aws": self.is_aws,
            "is_azure": self.is_azure,
            "is_gcp": self.is_gcp,
        }