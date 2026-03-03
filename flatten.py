"""Helper module for a simple speckle object tree flattening."""

from collections.abc import Iterable
from typing import Set, Optional

from specklepy.objects import Base


def flatten_base(base: Base, visited: Optional[Set[str]] = None) -> Iterable[Base]:
    """Flatten a base object into an iterable of all nested Base objects.

    This function recursively traverses all properties of the base object,
    yielding each nested Base object found. Handles Grasshopper collections
    and various Speckle data structures.

    Args:
        base (Base): The base object to flatten.
        visited: Set of already visited object IDs to prevent infinite loops.

    Yields:
        Base: Each nested base object in the hierarchy.
    """
    if visited is None:
        visited = set()
    
    # Handle None input
    if base is None:
        return
    
    # Skip if already visited (prevent infinite loops)
    obj_id = getattr(base, "id", None) or str(id(base))
    if obj_id in visited:
        return
    visited.add(obj_id)
    
    # Yield the current object
    yield base
    
    # Container properties to check (common in Grasshopper and other connectors)
    container_props = [
        "elements", "@elements",
        "objects", "@objects", 
        "children", "@children",
        "displayValue", "@displayValue",
        "geometry", "@geometry",
        "definition", "@definition",
        "data", "@data",
    ]
    
    # Get dynamic member names if available
    dynamic_members = []
    try:
        if hasattr(base, "get_dynamic_member_names"):
            dynamic_members = list(base.get_dynamic_member_names())
        elif hasattr(base, "get_member_names"):
            dynamic_members = list(base.get_member_names())
    except Exception:
        pass
    
    all_props = set(container_props) | set(dynamic_members)
    
    for prop_name in all_props:
        value = None
        
        # Try getattr first
        try:
            value = getattr(base, prop_name, None)
        except Exception:
            pass
        
        # Try dict-style access for dynamic properties
        if value is None:
            try:
                value = base[prop_name]
            except (KeyError, TypeError, AttributeError):
                pass
            
        if value is None:
            continue
        
        # If it's a Base object, recurse
        if isinstance(value, Base):
            yield from flatten_base(value, visited)
        # If it's a list/tuple, check each element
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, Base):
                    yield from flatten_base(item, visited)
