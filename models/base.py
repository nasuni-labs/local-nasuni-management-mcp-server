#!/usr/bin/env python3
"""Base model classes for the MCP server."""

from typing import Dict, Any
from abc import ABC, abstractmethod


class BaseModel(ABC):
    """Base class for all data models."""
    
    def __init__(self, data: Dict[str, Any]):
        self._raw_data = data
        self._parse_data(data)
    
    @abstractmethod
    def _parse_data(self, data: Dict[str, Any]):
        """Parse the raw data into model attributes."""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary representation."""
        result = {}
        for key, value in self.__dict__.items():
            if key.startswith('_'):
                continue
            if isinstance(value, BaseModel):
                result[key] = value.to_dict()
            elif isinstance(value, list):
                result[key] = [
                    item.to_dict() if isinstance(item, BaseModel) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result
    
    def get_raw_data(self) -> Dict[str, Any]:
        """Get the original raw data."""
        return self._raw_data


class NestedModel(BaseModel):
    """Base class for nested model structures."""
    
    def __init__(self, data: Dict[str, Any] = None):
        if data is None:
            data = {}
        super().__init__(data)