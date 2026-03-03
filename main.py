"""Structural Pipe Radius Heatmap - Speckle Automate Function.

This function creates a visual heatmap in the Speckle Viewer based on
the radius of structural pipes, grouping them into 4 clusters.
"""

from typing import List

from specklepy.objects import Base
from speckle_automate import (
    AutomationContext,
    execute_automate_function,
)

from flatten import flatten_base


# Cluster thresholds (in meters)
CLUSTER_1_MIN = 0.40  # Optimal/Small: 0.40 <= radius < 0.65
CLUSTER_1_MAX = 0.65
CLUSTER_2_MAX = 0.95  # Standard/Medium: 0.65 <= radius < 0.95
CLUSTER_3_MAX = 1.25  # Heavy/Large: 0.95 <= radius < 1.25
# Cluster 4: Massive/Critical: radius >= 1.25


def automate_function(automate_context: AutomationContext) -> None:
    """Analyze structural pipes and create a visual heatmap based on Pipe_Radius.

    Groups pipes into 4 clusters based on their radius and applies visual
    feedback using semantic states (success, info, warning, error).

    Args:
        automate_context: Runtime context providing access to Speckle data
            and methods for attaching results.
    """
    # Receive the model version
    version_root_object = automate_context.receive_version()

    # Flatten and filter objects with Pipe_Radius property
    pipes_with_radius: List[Base] = [
        obj
        for obj in flatten_base(version_root_object)
        if hasattr(obj, "Pipe_Radius") and obj.Pipe_Radius is not None
    ]

    # Gracefully fail if no pipes with Pipe_Radius found
    if not pipes_with_radius:
        automate_context.mark_run_failed(
            "No objects with 'Pipe_Radius' property found in the model. "
            "Please ensure the model contains structural pipes with radius data."
        )
        return

    # Initialize clusters
    cluster_1_optimal: List[Base] = []  # 0.40 <= radius < 0.65
    cluster_2_standard: List[Base] = []  # 0.65 <= radius < 0.95
    cluster_3_heavy: List[Base] = []  # 0.95 <= radius < 1.25
    cluster_4_massive: List[Base] = []  # radius >= 1.25

    # Classify pipes into clusters
    for pipe in pipes_with_radius:
        radius = float(pipe.Pipe_Radius)

        if CLUSTER_1_MIN <= radius < CLUSTER_1_MAX:
            cluster_1_optimal.append(pipe)
        elif CLUSTER_1_MAX <= radius < CLUSTER_2_MAX:
            cluster_2_standard.append(pipe)
        elif CLUSTER_2_MAX <= radius < CLUSTER_3_MAX:
            cluster_3_heavy.append(pipe)
        elif radius >= CLUSTER_3_MAX:
            cluster_4_massive.append(pipe)
        # Note: pipes with radius < 0.40m are not categorized

    # Apply visual feedback to each cluster
    if cluster_1_optimal:
        automate_context.attach_success_to_objects(
            category="Radius 0.40m - 0.64m (Optimal)",
            affected_objects=cluster_1_optimal,
            message=f"{len(cluster_1_optimal)} pipes with small/optimal radius",
        )

    if cluster_2_standard:
        automate_context.attach_info_to_objects(
            category="Radius 0.65m - 0.94m (Standard)",
            affected_objects=cluster_2_standard,
            message=f"{len(cluster_2_standard)} pipes with standard/medium radius",
        )

    if cluster_3_heavy:
        automate_context.attach_warning_to_objects(
            category="Radius 0.95m - 1.24m (Heavy)",
            affected_objects=cluster_3_heavy,
            message=f"{len(cluster_3_heavy)} pipes with heavy/large radius",
        )

    if cluster_4_massive:
        automate_context.attach_error_to_objects(
            category="Radius >= 1.25m (Critical)",
            affected_objects=cluster_4_massive,
            message=f"{len(cluster_4_massive)} pipes with massive/critical radius",
        )

    # Build summary
    total_processed = (
        len(cluster_1_optimal)
        + len(cluster_2_standard)
        + len(cluster_3_heavy)
        + len(cluster_4_massive)
    )

    summary = (
        f"Processed {total_processed} structural pipes: "
        f"Optimal={len(cluster_1_optimal)}, "
        f"Standard={len(cluster_2_standard)}, "
        f"Heavy={len(cluster_3_heavy)}, "
        f"Critical={len(cluster_4_massive)}"
    )

    automate_context.mark_run_success(summary)


# Entry point
if __name__ == "__main__":
    execute_automate_function(automate_function)

    # If the function has no arguments, the executor can handle it like so
    # execute_automate_function(automate_function_without_inputs)
    
    


from speckle_automate import AutomateBase, AutomationContext, execute_automate_function
from flatten import flatten_base

class FunctionInputs(AutomateBase):
    # No user inputs required, the app runs automatically by reading the model properties
    pass 

def automate_function(automate_context: AutomationContext, function_inputs: FunctionInputs) -> None:
    # 1. Receive and flatten the incoming model data
    version_root = automate_context.receive_version()
    all_objects = flatten_base(version_root)

    # 2. Search for the exact property "Pipe_Radius"
    pipes = [obj for obj in all_objects if getattr(obj, "Pipe_Radius", None) is not None]

    if not pipes:
        automate_context.mark_run_failed("No elements with the 'Pipe_Radius' property were found in the model.")
        return

    # 3. Create the 4 Clusters in METERS (0.40m -> 1.50m)
    cluster_green = [p for p in pipes if 0.40 <= getattr(p, "Pipe_Radius", 0) < 0.65]
    cluster_blue = [p for p in pipes if 0.65 <= getattr(p, "Pipe_Radius", 0) < 0.95]
    cluster_yellow = [p for p in pipes if 0.95 <= getattr(p, "Pipe_Radius", 0) < 1.25]
    cluster_red = [p for p in pipes if getattr(p, "Pipe_Radius", 0) >= 1.25]

    # 4. Assign colors (Semantic States) in the Speckle Viewer
    if cluster_green:
        automate_context.attach_success_to_objects(
            category="Radius 0.40m - 0.64m", 
            affected_objects=cluster_green, 
            message="Optimal profile"
        )
    if cluster_blue:
        automate_context.attach_info_to_objects(
            category="Radius 0.65m - 0.94m", 
            affected_objects=cluster_blue, 
            message="Standard profile"
        )
    if cluster_yellow:
        automate_context.attach_warning_to_objects(
            category="Radius 0.95m - 1.24m", 
            affected_objects=cluster_yellow, 
            message="Heavy profile"
        )
    if cluster_red:
        automate_context.attach_error_to_objects(
            category="Radius >= 1.25m", 
            affected_objects=cluster_red, 
            message="Massive profile"
        )

    # 5. Final success message
    automate_context.mark_run_success(
        f"Heatmap successfully applied! Processed and color-coded {len(pipes)} structural elements."
    )

if __name__ == "__main__":
    execute_automate_function(automate_function, FunctionInputs)