"""This module contains the function's business logic.

Use the automation_context module to wrap your function in an Automate context helper.
"""

from pydantic import Field, SecretStr
from speckle_automate import (
    AutomateBase,
    AutomationContext,
    execute_automate_function,
)

from flatten import flatten_base


class FunctionInputs(AutomateBase):
    """These are function author-defined values.

    Automate will make sure to supply them matching the types specified here.
    Please use the pydantic model schema to define your inputs:
    https://docs.pydantic.dev/latest/usage/models/
    """

    # An example of how to use secret values.
    whisper_message: SecretStr = Field(title="This is a secret message")
    forbidden_speckle_type: str = Field(
        title="Forbidden speckle type",
        description=(
            "If a object has the following speckle_type,"
            " it will be marked with an error."
        ),
    )


def automate_function(
    automate_context: AutomationContext,
    function_inputs: FunctionInputs,
) -> None:
    """This is an example Speckle Automate function.

    Args:
        automate_context: A context-helper object that carries relevant information
            about the runtime context of this function.
            It gives access to the Speckle project data that triggered this run.
            It also has convenient methods for attaching results to the Speckle model.
        function_inputs: An instance object matching the defined schema.
    """
    # The context provides a convenient way to receive the triggering version.
    version_root_object = automate_context.receive_version()

    objects_with_forbidden_speckle_type = [
        b
        for b in flatten_base(version_root_object)
        if b.speckle_type == function_inputs.forbidden_speckle_type
    ]
    count = len(objects_with_forbidden_speckle_type)

    if count > 0:
        # This is how a run is marked with a failure cause.
        automate_context.attach_error_to_objects(
            category="Forbidden speckle_type"
            f" ({function_inputs.forbidden_speckle_type})",
            affected_objects=objects_with_forbidden_speckle_type,
            message="This project should not contain the type: "
            f"{function_inputs.forbidden_speckle_type}",
        )
        automate_context.mark_run_failed(
            "Automation failed: "
            f"Found {count} object that have one of the forbidden speckle types: "
            f"{function_inputs.forbidden_speckle_type}"
        )

        # Set the automation context view to the original model/version view
        # to show the offending objects.
        automate_context.set_context_view()

    else:
        automate_context.mark_run_success("No forbidden types found.")

    # If the function generates file results, this is how it can be
    # attached to the Speckle project/model
    # automate_context.store_file_result("./report.pdf")


def automate_function_without_inputs(automate_context: AutomationContext) -> None:
    """A function example without inputs.

    If your function does not need any input variables,
     besides what the automation context provides,
     the inputs argument can be omitted.
    """
    pass


# make sure to call the function with the executor
if __name__ == "__main__":
    # NOTE: always pass in the automate function by its reference; do not invoke it!

    # Pass in the function reference with the inputs schema to the executor.
    execute_automate_function(automate_function, FunctionInputs)

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