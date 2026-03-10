"""Structural Analysis & Heatmap - Speckle Automate Function.

This function creates visual heatmaps in the Speckle Viewer based on:
- Pipe radius (4 clusters)
- Slab panel areas (3 clusters)
- High volume elements (flagged)

It also generates CSV/Excel reports for all structural data.
"""

import os
import tempfile
from typing import List, Optional, Tuple, Dict, Any

import pandas as pd
from specklepy.objects import Base
from speckle_automate import (
    AutomateBase,
    AutomationContext,
    execute_automate_function,
)

from flatten import flatten_base


class FunctionInputs(AutomateBase):
    """No user inputs required for this function.
    
    The clustering thresholds are predefined.
    """
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# PIPE RADIUS THRESHOLDS (in meters)
# ═══════════════════════════════════════════════════════════════════════════════
CLUSTER_1_MIN = 0.40  # Optimal/Small: 0.40 <= radius < 0.65
CLUSTER_1_MAX = 0.65
CLUSTER_2_MAX = 0.95  # Standard/Medium: 0.65 <= radius < 0.95
CLUSTER_3_MAX = 1.25  # Heavy/Large: 0.95 <= radius < 1.25
# Cluster 4: Massive/Critical: radius >= 1.25

# ═══════════════════════════════════════════════════════════════════════════════
# SLAB AREA THRESHOLDS (in square meters)
# ═══════════════════════════════════════════════════════════════════════════════
SLAB_SMALL_MAX = 50.0    # Small/Standard: area < 50
SLAB_MEDIUM_MAX = 150.0  # Medium: 50 <= area <= 150
# Massive: area > 150

# ═══════════════════════════════════════════════════════════════════════════════
# VOLUME THRESHOLD (in cubic meters)
# ═══════════════════════════════════════════════════════════════════════════════
HIGH_VOLUME_THRESHOLD = 10.0  # Elements with volume > 10 m³


# ═══════════════════════════════════════════════════════════════════════════════
# PROPERTY EXTRACTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_property_value(obj: Base, prop_names: List[str]) -> Optional[Any]:
    """Extract a property from an object, checking multiple possible locations.
    
    Handles Grasshopper data where properties are stored in nested 'properties' object.
    
    Args:
        obj: A Speckle Base object.
        prop_names: List of possible property names to search for.
        
    Returns:
        The property value, or None if not found.
    """
    def try_get_value(container, names: List[str]) -> Optional[Any]:
        if container is None:
            return None
        
        for name in names:
            value = None
            
            # Try getattr for Base objects
            if isinstance(container, Base):
                value = getattr(container, name, None)
                # Also try dict-style access for dynamic properties
                if value is None:
                    try:
                        value = container[name]
                    except (KeyError, TypeError):
                        pass
            # Try dict access
            elif isinstance(container, dict):
                value = container.get(name)
            
            if value is not None:
                # Handle parameter objects with 'value' property
                if hasattr(value, "value"):
                    return value.value
                return value
        
        return None
    
    # 1. Try direct property access on the object
    result = try_get_value(obj, prop_names)
    if result is not None:
        return result
    
    # 2. Try nested in 'properties' (Grasshopper data structure)
    properties = getattr(obj, "properties", None)
    if properties is None:
        try:
            properties = obj["properties"]
        except (KeyError, TypeError):
            pass
    
    result = try_get_value(properties, prop_names)
    if result is not None:
        return result
    
    # 3. Try nested in '@properties'
    properties = getattr(obj, "@properties", None)
    result = try_get_value(properties, prop_names)
    if result is not None:
        return result
    
    # 4. Try nested in 'parameters' (Revit data)
    parameters = getattr(obj, "parameters", None)
    result = try_get_value(parameters, prop_names)
    if result is not None:
        return result
    
    return None


def get_float_property(obj: Base, prop_names: List[str]) -> Optional[float]:
    """Extract a float property from an object."""
    value = get_property_value(obj, prop_names)
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def get_pipe_radius(obj: Base) -> Optional[float]:
    """Extract Pipe_Radius from an object."""
    return get_float_property(obj, ["Pipe_Radius", "pipe_radius", "PipeRadius", "pipeRadius"])


def get_area(obj: Base) -> Optional[float]:
    """Extract area from an object."""
    return get_float_property(obj, ["area", "Area", "AREA", "surface_area", "SurfaceArea"])


def get_volume(obj: Base) -> Optional[float]:
    """Extract volume from an object."""
    return get_float_property(obj, ["volume", "Volume", "VOLUME"])


def get_thickness(obj: Base) -> Optional[float]:
    """Extract thickness from an object."""
    return get_float_property(obj, ["thickness", "Thickness", "THICKNESS", "depth", "Depth"])


def get_length(obj: Base) -> Optional[float]:
    """Extract length from an object."""
    return get_float_property(obj, ["length", "Length", "LENGTH", "Pipe_Lenght", "pipe_length"])


def get_height(obj: Base) -> Optional[float]:
    """Extract height from an object."""
    return get_float_property(obj, ["height", "Height", "HEIGHT"])


def get_weight(obj: Base) -> Optional[float]:
    """Extract weight from an object."""
    return get_float_property(obj, ["weight", "Weight", "WEIGHT", "mass", "Mass"])


def get_material(obj: Base) -> Optional[str]:
    """Extract material from an object."""
    value = get_property_value(obj, ["material", "Material", "MATERIAL", "materialName"])
    if value is not None:
        return str(value)
    return None


def get_name(obj: Base) -> Optional[str]:
    """Extract name from an object."""
    value = get_property_value(obj, ["name", "Name", "NAME"])
    if value is not None:
        return str(value)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ELEMENT CATEGORIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def categorize_element(obj: Base) -> str:
    """Categorize an element based on its properties.
    
    Returns:
        Category name: 'Pipe', 'Slab', 'Core', 'Diagrid', 'Beam', 'Column', or 'Other'
    """
    # Check for pipe radius first (specific to this model)
    if get_pipe_radius(obj) is not None:
        return "Diagrid_Pipe"
    
    # Check speckle_type if available
    speckle_type = getattr(obj, "speckle_type", "") or ""
    name = get_name(obj) or ""
    
    # Check by name patterns
    name_lower = name.lower()
    if "slab" in name_lower or "floor" in name_lower:
        return "Slab"
    if "core" in name_lower or "wall" in name_lower:
        return "Core"
    if "diagrid" in name_lower or "pipe" in name_lower:
        return "Diagrid_Pipe"
    if "beam" in name_lower:
        return "Beam"
    if "column" in name_lower:
        return "Column"
    
    # Check by speckle_type
    if "Floor" in speckle_type or "Slab" in speckle_type:
        return "Slab"
    if "Wall" in speckle_type:
        return "Core"
    if "Beam" in speckle_type:
        return "Beam"
    if "Column" in speckle_type:
        return "Column"
    if "Pipe" in speckle_type:
        return "Diagrid_Pipe"
    
    # Check by available properties
    has_area = get_area(obj) is not None
    has_thickness = get_thickness(obj) is not None
    has_height = get_height(obj) is not None
    has_length = get_length(obj) is not None
    
    if has_area and has_thickness and not has_height:
        return "Slab"
    if has_height and not has_length:
        return "Core"
    if has_length:
        return "Diagrid_Pipe"
    
    return "Other"


def extract_element_data(obj: Base) -> Dict[str, Any]:
    """Extract all available structural properties from an element."""
    return {
        "id": getattr(obj, "id", None),
        "name": get_name(obj),
        "speckle_type": getattr(obj, "speckle_type", None),
        "category": categorize_element(obj),
        "area": get_area(obj),
        "volume": get_volume(obj),
        "thickness": get_thickness(obj),
        "length": get_length(obj),
        "height": get_height(obj),
        "weight": get_weight(obj),
        "material": get_material(obj),
        "pipe_radius": get_pipe_radius(obj),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_reports(
    all_elements_data: List[Dict[str, Any]],
    automate_context: AutomationContext
) -> int:
    """Generate CSV and Excel reports for all structural categories.
    
    Args:
        all_elements_data: List of element data dictionaries.
        automate_context: The automation context for storing files.
        
    Returns:
        Number of files generated.
    """
    files_generated = 0
    temp_dir = tempfile.mkdtemp()
    
    # Create main DataFrame
    df_all = pd.DataFrame(all_elements_data)
    
    if df_all.empty:
        return 0
    
    # Group by category
    categories = df_all["category"].unique()
    category_dfs: Dict[str, pd.DataFrame] = {}
    
    for category in categories:
        df_category = df_all[df_all["category"] == category].copy()
        
        # Add summary statistics
        summary_row = {
            "id": "SUMMARY",
            "name": f"Total {category} Elements",
            "speckle_type": "",
            "category": category,
            "area": df_category["area"].sum() if "area" in df_category else None,
            "volume": df_category["volume"].sum() if "volume" in df_category else None,
            "thickness": None,
            "length": df_category["length"].sum() if "length" in df_category else None,
            "height": None,
            "weight": df_category["weight"].sum() if "weight" in df_category else None,
            "material": f"Count: {len(df_category)}",
            "pipe_radius": None,
        }
        
        # Append summary row
        df_with_summary = pd.concat([df_category, pd.DataFrame([summary_row])], ignore_index=True)
        category_dfs[category] = df_with_summary
        
        # Generate individual CSV
        csv_filename = f"Structural_Data_{category}.csv"
        csv_path = os.path.join(temp_dir, csv_filename)
        df_with_summary.to_csv(csv_path, index=False)
        
        try:
            automate_context.store_file_result(csv_path)
            files_generated += 1
        except Exception:
            pass
    
    # Generate Master Excel with multiple sheets
    excel_path = os.path.join(temp_dir, "Structural_Master_Report.xlsx")
    
    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            # Summary sheet
            summary_data = []
            for category, df in category_dfs.items():
                element_count = len(df) - 1  # Exclude summary row
                total_area = df["area"].iloc[:-1].sum() if "area" in df else 0
                total_volume = df["volume"].iloc[:-1].sum() if "volume" in df else 0
                summary_data.append({
                    "Category": category,
                    "Element Count": element_count,
                    "Total Area (m²)": round(total_area, 2) if pd.notna(total_area) else 0,
                    "Total Volume (m³)": round(total_volume, 2) if pd.notna(total_volume) else 0,
                })
            
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name="Summary", index=False)
            
            # Individual category sheets
            for category, df in category_dfs.items():
                # Truncate sheet name to 31 chars (Excel limit)
                sheet_name = category[:31]
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        automate_context.store_file_result(excel_path)
        files_generated += 1
    except Exception:
        pass
    
    # Cleanup temp files
    try:
        for f in os.listdir(temp_dir):
            os.remove(os.path.join(temp_dir, f))
        os.rmdir(temp_dir)
    except Exception:
        pass
    
    return files_generated


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN AUTOMATE FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def automate_function(
    automate_context: AutomationContext,
    function_inputs: FunctionInputs,
) -> None:
    """Analyze structural elements and create visual heatmaps.

    Features:
    1. Pipe Radius Heatmap (4 clusters)
    2. Slab Panel Area Heatmap (3 clusters)
    3. High Volume Element Flags
    4. CSV/Excel Report Generation

    Args:
        automate_context: Runtime context providing access to Speckle data.
        function_inputs: Function inputs (not used in this function).
    """
    _ = function_inputs  # Unused, but required by SDK
    
    try:
        # ═══════════════════════════════════════════════════════════════════════
        # 1. RECEIVE AND FLATTEN MODEL DATA
        # ═══════════════════════════════════════════════════════════════════════
        version_root_object = automate_context.receive_version()
        all_objects = list(flatten_base(version_root_object))
        
        # Extract data from all objects for reporting
        all_elements_data: List[Dict[str, Any]] = []
        for obj in all_objects:
            data = extract_element_data(obj)
            # Only include objects with at least some meaningful data
            if any(v is not None for k, v in data.items() if k not in ["id", "category"]):
                all_elements_data.append(data)
        
        # ═══════════════════════════════════════════════════════════════════════
        # 2. PIPE RADIUS HEATMAP (EXISTING LOGIC - PRESERVED)
        # ═══════════════════════════════════════════════════════════════════════
        pipes_with_radius: List[Tuple[Base, float]] = []
        
        for obj in all_objects:
            radius = get_pipe_radius(obj)
            if radius is not None:
                pipes_with_radius.append((obj, radius))

        # Initialize pipe clusters
        cluster_1_optimal: List[Base] = []  # 0.40 <= radius < 0.65
        cluster_2_standard: List[Base] = []  # 0.65 <= radius < 0.95
        cluster_3_heavy: List[Base] = []  # 0.95 <= radius < 1.25
        cluster_4_massive: List[Base] = []  # radius >= 1.25

        # Classify pipes into clusters
        for pipe, radius in pipes_with_radius:
            if CLUSTER_1_MIN <= radius < CLUSTER_1_MAX:
                cluster_1_optimal.append(pipe)
            elif CLUSTER_1_MAX <= radius < CLUSTER_2_MAX:
                cluster_2_standard.append(pipe)
            elif CLUSTER_2_MAX <= radius < CLUSTER_3_MAX:
                cluster_3_heavy.append(pipe)
            elif radius >= CLUSTER_3_MAX:
                cluster_4_massive.append(pipe)

        # Apply visual feedback to pipe clusters
        if cluster_1_optimal:
            automate_context.attach_success_to_objects(
                category="Pipe Radius 0.40m - 0.64m (Optimal)",
                affected_objects=cluster_1_optimal,
                message=f"{len(cluster_1_optimal)} pipes with small/optimal radius",
            )

        if cluster_2_standard:
            automate_context.attach_info_to_objects(
                category="Pipe Radius 0.65m - 0.94m (Standard)",
                affected_objects=cluster_2_standard,
                message=f"{len(cluster_2_standard)} pipes with standard/medium radius",
            )

        if cluster_3_heavy:
            automate_context.attach_warning_to_objects(
                category="Pipe Radius 0.95m - 1.24m (Heavy)",
                affected_objects=cluster_3_heavy,
                message=f"{len(cluster_3_heavy)} pipes with heavy/large radius",
            )

        if cluster_4_massive:
            automate_context.attach_error_to_objects(
                category="Pipe Radius >= 1.25m (Critical)",
                affected_objects=cluster_4_massive,
                message=f"{len(cluster_4_massive)} pipes with massive/critical radius",
            )

        total_pipes = (
            len(cluster_1_optimal)
            + len(cluster_2_standard)
            + len(cluster_3_heavy)
            + len(cluster_4_massive)
        )

        # ═══════════════════════════════════════════════════════════════════════
        # 3. SLAB PANEL AREA HEATMAP (NEW)
        # ═══════════════════════════════════════════════════════════════════════
        slabs_with_area: List[Tuple[Base, float]] = []
        
        for obj in all_objects:
            area = get_area(obj)
            if area is not None and area > 0:
                slabs_with_area.append((obj, area))
        
        # Initialize slab clusters
        slab_small: List[Base] = []   # area < 50
        slab_medium: List[Base] = []  # 50 <= area <= 150
        slab_massive: List[Base] = []  # area > 150
        
        for slab, area in slabs_with_area:
            if area < SLAB_SMALL_MAX:
                slab_small.append(slab)
            elif area <= SLAB_MEDIUM_MAX:
                slab_medium.append(slab)
            else:
                slab_massive.append(slab)
        
        # Apply visual feedback to slab clusters
        if slab_small:
            automate_context.attach_success_to_objects(
                category="Slab Area < 50m² (Small)",
                affected_objects=slab_small,
                message=f"{len(slab_small)} panels - Optimal Pouring Size",
            )
        
        if slab_medium:
            automate_context.attach_info_to_objects(
                category="Slab Area 50-150m² (Medium)",
                affected_objects=slab_medium,
                message=f"{len(slab_medium)} panels - Standard Pouring Size",
            )
        
        if slab_massive:
            automate_context.attach_warning_to_objects(
                category="Slab Area > 150m² (Large)",
                affected_objects=slab_massive,
                message=f"{len(slab_massive)} panels - Large Surface Area - Review for Expansion Joints or Phased Pouring",
            )
        
        total_slabs = len(slab_small) + len(slab_medium) + len(slab_massive)

        # ═══════════════════════════════════════════════════════════════════════
        # 4. MASSIVE VOLUME FLAG (NEW)
        # ═══════════════════════════════════════════════════════════════════════
        high_volume_elements: List[Base] = []
        
        for obj in all_objects:
            volume = get_volume(obj)
            if volume is not None and volume > HIGH_VOLUME_THRESHOLD:
                high_volume_elements.append(obj)
        
        if high_volume_elements:
            automate_context.attach_error_to_objects(
                category="High Volume (> 10m³)",
                affected_objects=high_volume_elements,
                message=f"{len(high_volume_elements)} elements - High Material Intensity Element - Review for Optimization",
            )

        # ═══════════════════════════════════════════════════════════════════════
        # 5. GENERATE REPORTS (NEW)
        # ═══════════════════════════════════════════════════════════════════════
        files_generated = generate_reports(all_elements_data, automate_context)

        # ═══════════════════════════════════════════════════════════════════════
        # 6. SET CONTEXT VIEW AND MARK SUCCESS
        # ═══════════════════════════════════════════════════════════════════════
        automate_context.set_context_view()

        # Build comprehensive summary
        summary_parts = []
        
        if total_pipes > 0:
            summary_parts.append(
                f"Pipe Radius Heatmap: {total_pipes} pipes "
                f"(Optimal={len(cluster_1_optimal)}, Standard={len(cluster_2_standard)}, "
                f"Heavy={len(cluster_3_heavy)}, Critical={len(cluster_4_massive)})"
            )
        
        if total_slabs > 0:
            summary_parts.append(
                f"Slab Area Heatmap: {total_slabs} panels "
                f"(Small={len(slab_small)}, Medium={len(slab_medium)}, Large={len(slab_massive)})"
            )
        
        if high_volume_elements:
            summary_parts.append(f"High Volume Flags: {len(high_volume_elements)} elements")
        
        if files_generated > 0:
            summary_parts.append(f"Reports Generated: {files_generated} files")
        
        if summary_parts:
            summary = " | ".join(summary_parts)
        else:
            summary = "Analysis complete. No structural elements with processable data found."
        
        automate_context.mark_run_success(summary)
        
    except Exception as e:
        automate_context.mark_run_exception(f"Unexpected error: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    execute_automate_function(automate_function, FunctionInputs)
