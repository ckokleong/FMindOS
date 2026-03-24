from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SemanticMap:
    name: str
    map_id: Optional[int] = None
    aliases: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class SemanticLocation:
    name: str
    map_name: Optional[str] = None
    map_id: Optional[int] = None
    waypoint_name: Optional[str] = None
    waypoint_id: Optional[int] = None
    location_type: str = "waypoint"
    description: str = ""
    category: str = ""
    aliases: List[str] = field(default_factory=list)
    task_hints: List[str] = field(default_factory=list)
    relations: List[Dict[str, str]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticWorld:
    name: str = "default"
    description: str = ""
    default_map_name: Optional[str] = None
    default_map_id: Optional[int] = None
    maps: List[SemanticMap] = field(default_factory=list)
    locations: List[SemanticLocation] = field(default_factory=list)


@dataclass
class ResolvedMap:
    query: str
    name: str
    map_id: Optional[int] = None
    source: str = "unknown"
    score: int = 0
    aliases: List[str] = field(default_factory=list)


@dataclass
class ResolvedLocation:
    query: str
    name: str
    map_name: Optional[str] = None
    map_id: Optional[int] = None
    waypoint_name: Optional[str] = None
    waypoint_id: Optional[int] = None
    location_type: str = "waypoint"
    description: str = ""
    category: str = ""
    task_hints: List[str] = field(default_factory=list)
    relations: List[Dict[str, str]] = field(default_factory=list)
    source: str = "unknown"
    score: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
