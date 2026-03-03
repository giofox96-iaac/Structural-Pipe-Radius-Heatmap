"""Helper module for a simple speckle object tree flattening."""

from collections.abc import Iterable
from typing import Set

from specklepy.objects import Base


def flatten_base(base: Base, visited: Set[str] = None) -> Iterable[Base]:
    """Flatten a base object into an iterable of all nested Base objects.

    This function recursively traverses all properties of the base object,
    yielding each nested Base object found.

    Args:
        base (Base): The base object to flatten.
        visited: Set of already visited object IDs to prevent infinite loops.

    Yields:
        Base: Each nested base object in the hierarchy.
    """
    if visited is None:
        visited = set()
    
    # Skip if already visited (prevent infinite loops)
    obj_id = getattr(base, "id", id(base))
    if obj_id in visited:
        return
    visited.add(obj_id)
    
    # Yield the current object first
    yield base
    
    # Get all member names (properties) of this Base object
    try:
        member_names = base.get_member_names() if hasattr(base, "get_member_names") else []
    except Exception:
        member_names = []
    
    # Also check common container properties
    common_props = ["elements", "@elements", "displayValue", "@displayValue", 
                    "children", "@children", "objects", "@objects"]
    
    all_props = set(member_names) | set(common_props)
    
    for prop_name in all_props:
        try:
            value = getattr(base, prop_name, None)
        except Exception:
            continue
            
        if value is None:
            continue
        
        # If it's a Base object, recurse
        if isinstance(value, Base):
            yield from flatten_base(value, visited)
        # If it's a list, check each element
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, Base):
                    yield from flatten_base(item, visited)
