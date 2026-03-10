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

from flatten import flatten_base, flatten_base_with_collection


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
# SLAB AREA THRESHOLDS (Floor_Slab_Area values)
# ═══════════════════════════════════════════════════════════════════════════════
SLAB_CLUSTER_1_MAX = 1500.0    # Cluster 1: area < 1500
SLAB_CLUSTER_2_MAX = 5000.0    # Cluster 2: 1500 <= area < 5000
SLAB_CLUSTER_3_MAX = 12500.0   # Cluster 3: 5000 <= area < 12500
SLAB_CLUSTER_4_MAX = 25000.0   # Cluster 4: 12500 <= area < 25000
# Cluster 5: area >= 25000

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


# ═══════════════════════════════════════════════════════════════════════════════
# GRASSHOPPER PROPERTY GETTERS (exact names from Grasshopper script)
# ═══════════════════════════════════════════════════════════════════════════════

def get_structural_role(obj: Base) -> Optional[str]:
    """Extract Structural_Role from an object."""
    value = get_property_value(obj, ["Structural_Role"])
    return str(value) if value is not None else None


def get_material(obj: Base) -> Optional[str]:
    """Extract Material from an object."""
    value = get_property_value(obj, ["Material"])
    return str(value) if value is not None else None


def get_density(obj: Base) -> Optional[float]:
    """Extract Density (kg/m³) from an object."""
    return get_float_property(obj, ["Density (kg/m³)", "Density"])


# Pipe properties
def get_pipe_lenght(obj: Base) -> Optional[float]:
    """Extract Pipe_Lenght from an object (typo preserved from Grasshopper)."""
    return get_float_property(obj, ["Pipe_Lenght"])


# Joint properties
def get_joint_tipe(obj: Base) -> Optional[str]:
    """Extract Joint_Tipe from an object (typo preserved from Grasshopper)."""
    value = get_property_value(obj, ["Joint_Tipe"])
    return str(value) if value is not None else None


# Floor Slab properties
def get_floor_slab_area(obj: Base) -> Optional[float]:
    """Extract Floor_Slab_Area from an object."""
    return get_float_property(obj, ["Floor_Slab_Area"])


def get_floor_slab_thickness(obj: Base) -> Optional[float]:
    """Extract Floor_Slab_Thickness from an object."""
    return get_float_property(obj, ["Floor_Slab_Thickness"])


def get_floor_slab_volume(obj: Base) -> Optional[float]:
    """Extract Floor_Slab_Volume from an object."""
    return get_float_property(obj, ["Floor_Slab_Volume"])


# Core properties
def get_core_height(obj: Base) -> Optional[float]:
    """Extract Core_Height from an object."""
    return get_float_property(obj, ["Core_Height"])


# Cable properties
def get_cables_volume(obj: Base) -> Optional[float]:
    """Extract Cables_Volume from an object."""
    return get_float_property(obj, ["Cables_Volume"])


# Belt Truss properties
def get_truss_belt_volume(obj: Base) -> Optional[float]:
    """Extract Truss_Belt_Volume from an object."""
    return get_float_property(obj, ["Truss_Belt_Volume"])


def get_name(obj: Base) -> Optional[str]:
    """Extract name from an object."""
    value = get_property_value(obj, ["name", "Name", "NAME"])
    return str(value) if value is not None else None


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
    
    # Check for Floor Slab properties
    if get_floor_slab_area(obj) is not None:
        return "Floor_Slab"
    
    # Check for Core properties
    if get_core_height(obj) is not None:
        return "Core"
    
    # Check for Cable properties
    if get_cables_volume(obj) is not None:
        return "Cables"
    
    # Check for Belt Truss properties
    if get_truss_belt_volume(obj) is not None:
        return "Belt_Truss"
    
    # Check for Joint properties
    if get_joint_tipe(obj) is not None:
        return "Joint"
    
    # Check speckle_type if available
    speckle_type = getattr(obj, "speckle_type", "") or ""
    name = get_name(obj) or ""
    
    # Check by name patterns
    name_lower = name.lower()
    if "slab" in name_lower or "floor" in name_lower:
        return "Floor_Slab"
    if "core" in name_lower or "wall" in name_lower:
        return "Core"
    if "diagrid" in name_lower or "pipe" in name_lower:
        return "Diagrid_Pipe"
    if "beam" in name_lower:
        return "Beam"
    if "column" in name_lower:
        return "Column"
    if "cable" in name_lower:
        return "Cables"
    if "truss" in name_lower:
        return "Belt_Truss"
    if "joint" in name_lower:
        return "Joint"
    
    # Check by speckle_type
    if "Floor" in speckle_type or "Slab" in speckle_type:
        return "Floor_Slab"
    if "Wall" in speckle_type:
        return "Core"
    if "Beam" in speckle_type:
        return "Beam"
    if "Column" in speckle_type:
        return "Column"
    if "Pipe" in speckle_type:
        return "Diagrid_Pipe"
    
    return "Other"


def extract_element_data(obj: Base, collection_name: Optional[str] = None) -> Dict[str, Any]:
    """Extract Grasshopper-specific properties from an element.
    
    Properties per collection (from Grasshopper script):
    - Pipes: Structural_Role, Pipe_Lenght, Pipe_Radius, Material, Density
    - Joints: Structural_Role, Joint_Tipe, Material, Density
    - Floor Slabs: Structural_Role, Material, Floor_Slab_Area, Floor_Slab_Thickness, Floor_Slab_Volume, Density
    - Cores: Structural_Role, Material, Density, Core_Height
    - Cables: Structural_Role, Material, Density, Cables_Volume
    - Belt Truss: Structural_Role, Material, Density, Truss_Belt_Volume
    """
    return {
        "id": getattr(obj, "id", None),
        "collection": collection_name,
        # Common properties
        "Structural_Role": get_structural_role(obj),
        "Material": get_material(obj),
        "Density (kg/m³)": get_density(obj),
        # Pipe properties
        "Pipe_Radius": get_pipe_radius(obj),
        "Pipe_Lenght": get_pipe_lenght(obj),
        # Joint properties
        "Joint_Tipe": get_joint_tipe(obj),
        # Floor Slab properties
        "Floor_Slab_Area": get_floor_slab_area(obj),
        "Floor_Slab_Thickness": get_floor_slab_thickness(obj),
        "Floor_Slab_Volume": get_floor_slab_volume(obj),
        # Core properties
        "Core_Height": get_core_height(obj),
        # Cable properties
        "Cables_Volume": get_cables_volume(obj),
        # Belt Truss properties
        "Truss_Belt_Volume": get_truss_belt_volume(obj),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_reports(
    all_elements_data: List[Dict[str, Any]],
    automate_context: AutomationContext
) -> int:
    """Generate CSV and Excel reports with Grasshopper data.
    
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
    
    # Group by collection
    collections = df_all["collection"].dropna().unique()
    collection_dfs: Dict[str, pd.DataFrame] = {}
    
    for collection in collections:
        df_collection = df_all[df_all["collection"] == collection].copy()
        collection_dfs[collection] = df_collection
        
        # Generate individual CSV per collection
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in collection)
        csv_filename = f"Structural_Data_{safe_name}.csv"
        csv_path = os.path.join(temp_dir, csv_filename)
        df_collection.to_csv(csv_path, index=False)
        
        try:
            automate_context.store_file_result(csv_path)
            files_generated += 1
        except Exception:
            pass
    
    # Also save all data combined
    all_csv_path = os.path.join(temp_dir, "Structural_Data_All_Elements.csv")
    df_all.to_csv(all_csv_path, index=False)
    try:
        automate_context.store_file_result(all_csv_path)
        files_generated += 1
    except Exception:
        pass
    
    # Generate Master Excel with multiple sheets
    excel_path = os.path.join(temp_dir, "Structural_Master_Report.xlsx")
    
    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            # Summary sheet
            summary_data = []
            for collection, df in collection_dfs.items():
                element_count = len(df)
                # Sum relevant columns based on what's available
                total_pipe_length = df["Pipe_Lenght"].sum() if "Pipe_Lenght" in df.columns else 0
                total_slab_area = df["Floor_Slab_Area"].sum() if "Floor_Slab_Area" in df.columns else 0
                total_slab_volume = df["Floor_Slab_Volume"].sum() if "Floor_Slab_Volume" in df.columns else 0
                total_cables_volume = df["Cables_Volume"].sum() if "Cables_Volume" in df.columns else 0
                total_truss_volume = df["Truss_Belt_Volume"].sum() if "Truss_Belt_Volume" in df.columns else 0
                
                summary_data.append({
                    "Collection": collection,
                    "Element Count": element_count,
                    "Total Pipe_Lenght": round(total_pipe_length, 2) if pd.notna(total_pipe_length) else 0,
                    "Total Floor_Slab_Area": round(total_slab_area, 2) if pd.notna(total_slab_area) else 0,
                    "Total Floor_Slab_Volume": round(total_slab_volume, 2) if pd.notna(total_slab_volume) else 0,
                    "Total Cables_Volume": round(total_cables_volume, 2) if pd.notna(total_cables_volume) else 0,
                    "Total Truss_Belt_Volume": round(total_truss_volume, 2) if pd.notna(total_truss_volume) else 0,
                })
            
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name="Summary", index=False)
            
            # Individual collection sheets
            for collection, df in collection_dfs.items():
                # Truncate sheet name to 31 chars (Excel limit)
                sheet_name = collection[:31]
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # All data sheet
            df_all.to_excel(writer, sheet_name="All Elements", index=False)
        
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
        # 1. RECEIVE AND FLATTEN MODEL DATA (WITH COLLECTION TRACKING)
        # ═══════════════════════════════════════════════════════════════════════
        version_root_object = automate_context.receive_version()
        
        # Get all objects with their collection names
        all_objects_with_collection = list(flatten_base_with_collection(version_root_object))
        all_objects = [obj for obj, _ in all_objects_with_collection]
        
        # Extract data from all objects for reporting (with collection info)
        all_elements_data: List[Dict[str, Any]] = []
        for obj, collection_name in all_objects_with_collection:
            data = extract_element_data(obj, collection_name)
            # Only include objects with at least some meaningful Grasshopper data
            if any(v is not None for k, v in data.items() if k not in ["id", "collection"]):
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
        # 3. SLAB PANEL AREA HEATMAP (ONLY "Floor Slabs" COLLECTION)
        # ═══════════════════════════════════════════════════════════════════════
        slabs_with_area: List[Tuple[Base, float]] = []
        
        # Debug: collect unique collection names
        collection_names_found = set()
        for _, coll_name in all_objects_with_collection:
            if coll_name:
                collection_names_found.add(coll_name)
        
        # Filter to only objects from "Floor Slabs" collection (case-insensitive)
        for obj, collection_name in all_objects_with_collection:
            if collection_name and "floor" in collection_name.lower() and "slab" in collection_name.lower():
                area = get_floor_slab_area(obj)
                if area is not None and area > 0:
                    slabs_with_area.append((obj, area))
        
        # Initialize slab clusters (5 clusters with thresholds: 1500, 5000, 12500, 25000)
        slab_cluster_1: List[Base] = []   # area < 1500
        slab_cluster_2: List[Base] = []   # 1500 <= area < 5000
        slab_cluster_3: List[Base] = []   # 5000 <= area < 12500
        slab_cluster_4: List[Base] = []   # 12500 <= area < 25000
        slab_cluster_5: List[Base] = []   # area >= 25000
        
        for slab, area in slabs_with_area:
            if area < SLAB_CLUSTER_1_MAX:
                slab_cluster_1.append(slab)
            elif area < SLAB_CLUSTER_2_MAX:
                slab_cluster_2.append(slab)
            elif area < SLAB_CLUSTER_3_MAX:
                slab_cluster_3.append(slab)
            elif area < SLAB_CLUSTER_4_MAX:
                slab_cluster_4.append(slab)
            else:
                slab_cluster_5.append(slab)
        
        # Apply visual feedback to slab clusters
        if slab_cluster_1:
            automate_context.attach_success_to_objects(
                category="Slab Area < 1500 (Cluster 1)",
                affected_objects=slab_cluster_1,
                message=f"{len(slab_cluster_1)} panels - Small Panel",
            )
        
        if slab_cluster_2:
            automate_context.attach_info_to_objects(
                category="Slab Area 1500-5000 (Cluster 2)",
                affected_objects=slab_cluster_2,
                message=f"{len(slab_cluster_2)} panels - Standard Panel",
            )
        
        if slab_cluster_3:
            automate_context.attach_info_to_objects(
                category="Slab Area 5000-12500 (Cluster 3)",
                affected_objects=slab_cluster_3,
                message=f"{len(slab_cluster_3)} panels - Medium Panel",
            )
        
        if slab_cluster_4:
            automate_context.attach_warning_to_objects(
                category="Slab Area 12500-25000 (Cluster 4)",
                affected_objects=slab_cluster_4,
                message=f"{len(slab_cluster_4)} panels - Large Panel",
            )
        
        if slab_cluster_5:
            automate_context.attach_error_to_objects(
                category="Slab Area >= 25000 (Cluster 5)",
                affected_objects=slab_cluster_5,
                message=f"{len(slab_cluster_5)} panels - Extra Large Panel - Review Required",
            )
        
        total_slabs = (
            len(slab_cluster_1) + len(slab_cluster_2) + len(slab_cluster_3) +
            len(slab_cluster_4) + len(slab_cluster_5)
        )

        # ═══════════════════════════════════════════════════════════════════════
        # 4. HIGH VOLUME ELEMENTS FLAG
        # ═══════════════════════════════════════════════════════════════════════
        high_volume_elements: List[Base] = []
        
        for obj in all_objects:
            # Check any of the volume properties
            volume = (
                get_floor_slab_volume(obj) or
                get_cables_volume(obj) or
                get_truss_belt_volume(obj)
            )
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
                f"(C1={len(slab_cluster_1)}, C2={len(slab_cluster_2)}, C3={len(slab_cluster_3)}, "
                f"C4={len(slab_cluster_4)}, C5={len(slab_cluster_5)})"
            )
        else:
            # Debug: show what collections were found
            if collection_names_found:
                summary_parts.append(f"Collections found: {list(collection_names_found)[:5]}")
            else:
                summary_parts.append("No collections detected")
        
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
