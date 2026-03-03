# GitHub Copilot Instructions

This is a Speckle Automate Python function repository. Use these guidelines when generating or reviewing code.

## What is Speckle Automate?

Speckle Automate is a CI/CD platform that runs Python functions automatically when a Speckle model version is published.

- **Deployment**: Push code → Create GitHub Release (semver tag like `v1.0.0`) → GitHub Action builds Docker image → Speckle runs it
- **Infrastructure**: Linux containers, CPU-only, no GPU, no external inbound calls allowed
- **Runtime**: `main.py` contains the function; `pyproject.toml` defines dependencies

## Function Entry Point Pattern

Every `main.py` must follow this structure:

```python
from speckle_automate import (
    AutomateBase,
    AutomationContext,
    execute_automate_function,
)
from pydantic import Field

# 1. Define inputs (generates form in Speckle UI)
class FunctionInputs(AutomateBase):
    field_name: str = Field(
        title="Display Title",
        description="Help text"
    )

# 2. Define the function
def automate_function(
    automate_context: AutomationContext,
    function_inputs: FunctionInputs,
) -> None:
    # Get model data
    version_root_object = automate_context.receive_version()

    # Your logic here

    # MUST call one of these:
    automate_context.mark_run_success("message")
    # OR
    automate_context.mark_run_failed("error message")
    # OR
    automate_context.mark_run_exception("exception message")

# 3. Wire it up
if __name__ == "__main__":
    execute_automate_function(automate_function, FunctionInputs)
```

**Critical rule**: You MUST call exactly one of the `mark_run_*` methods at the end.

## Function Inputs

Inputs use Pydantic's `Field()` and generate a web form in Speckle.

### Supported input types

| Type     | Python      | Example                                  |
| -------- | ----------- | ---------------------------------------- |
| Text     | `str`       | `field: str = Field(title="Name")`       |
| Number   | `float`     | `threshold: float = Field(gt=0, lt=100)` |
| Integer  | `int`       | `count: int = Field(ge=1)`               |
| Boolean  | `bool`      | `enabled: bool = Field(default=True)`    |
| Dropdown | `Enum`      | Use `from enum import Enum`              |
| Secret   | `SecretStr` | `api_key: SecretStr = Field(...)`        |

### Input validation

- `Field(...)` = required (no default)
- `Field(default=value)` = optional
- `gt=N, lt=M` = numeric range (greater than, less than)
- `ge=N, le=M` = numeric range (greater than or equal, less than or equal)
- `min_length=1, max_length=100` = string length
- `pattern=r"^[A-Z]+$"` = regex pattern

## AutomationContext Methods

The `automate_context` parameter provides your interface to Speckle:

### Accessing data

```python
version_root_object = automate_context.receive_version()  # Get model
```

### Reporting results (MUST call one)

```python
automate_context.mark_run_success("All tests passed")
automate_context.mark_run_failed("3 objects failed validation")
automate_context.mark_run_exception("Unexpected error occurred")
```

**Important**: Only the last status call is recorded. Don't call multiple.

### Annotating objects

```python
automate_context.attach_error_to_objects(
    category="Rule Name",
    affected_objects=obj_list,  # Base or List[Base]
    message="What went wrong",
    metadata={"key": "value"}
)

automate_context.attach_warning_to_objects(category="...", affected_objects=..., message="...")
automate_context.attach_success_to_objects(category="...", affected_objects=..., message="...")
automate_context.attach_info_to_objects(category="...", affected_objects=..., message="...")
```

**Best practices**:

- Group related errors together, don't create one per object
- Use `affected_objects` parameter (pass Base objects, not IDs)
- Keep category names consistent for related checks

### Creating new versions

```python
automate_context.create_new_version_in_project(
    root_object=modified_root,
    model_id="target-model-id",
    version_message="What changed"
)
```

### Saving reports/files

```python
url = automate_context.store_file_result("/tmp/report.pdf")
```

## Working with Speckle Objects

### Flattening the object tree

```python
from flatten import flatten_base

version_root_object = automate_context.receive_version()

# Iterate all objects
for obj in flatten_base(version_root_object):
    if obj.speckle_type == "Objects.BuiltElements.Wall":
        # process wall
        pass

# Filter by type
walls = [obj for obj in flatten_base(version_root_object)
         if obj.speckle_type == "Objects.BuiltElements.Wall"]
```

### Common speckle_type values

- `Objects.BuiltElements.Wall`
- `Objects.BuiltElements.Floor`
- `Objects.BuiltElements.Beam`
- `Objects.BuiltElements.Column`
- `Objects.BuiltElements.Door`
- `Objects.BuiltElements.Window`
- `Objects.BuiltElements.Room`
- `Objects.BuiltElements.Roof`
- `Objects.BuiltElements.Duct`
- `Objects.BuiltElements.Pipe`
- `Objects.Geometry.Mesh`
- `Objects.Geometry.Line`
- `Objects.Geometry.Point`

### Accessing object properties

```python
obj.id                      # Object ID
obj.speckle_type            # Type string
obj.applicationId           # Original ID from source app
obj.parameters              # BIM properties (if present)
obj.displayValue            # Geometry meshes (if present)
```

## Dependencies

Edit `pyproject.toml`:

- Runtime dependencies go in `[project] dependencies`
- Dev/test dependencies go in `[project.optional-dependencies] dev`

Example:

```toml
[project]
dependencies = [
    "specklepy==3.0.0",
    "pandas>=2.0.0",
]

[project.optional-dependencies]
dev = ["pytest", "black", "pytest-mock"]
```

## Testing Locally

Create `.env`:

```
SPECKLE_TOKEN=your_personal_access_token
SPECKLE_SERVER_URL=https://app.speckle.systems/
SPECKLE_PROJECT_ID=your_project_id
SPECKLE_AUTOMATION_ID=your_automation_id
```

Run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install .[dev]
pytest
```

## Deployment

1. Make changes in `main.py`
2. Push to GitHub
3. Create a GitHub Release with semver tag (`v1.0.0`, `v1.1.0`, etc.)
4. GitHub Action (`.github/workflows/main.yml`) auto-builds and deploys
5. New version appears in Speckle Functions Library

## Key Constraints

- **No GPU** — CPU compute only
- **Linux only** — containers run on Linux
- **No external inbound calls** — can't receive webhooks
- **Token-based auth** — use `SecretStr` for sensitive data
- **Functions are immutable** — can't be deleted once created
- **Updating version loses input values** — automation settings reset on new version

## Key Imports

```python
from speckle_automate import (
    AutomateBase,               # Base for FunctionInputs
    AutomationContext,          # Runtime context
    execute_automate_function,  # Entry point wiring
)
from pydantic import Field, SecretStr
from enum import Enum
from flatten import flatten_base
from specklepy.objects import Base
```

## Documentation

- Full Reference: https://docs.speckle.systems/developers/automate/
- Python Template: https://github.com/specklesystems/speckle_automate_python_example
- SpecklePy SDK: https://specklepy.speckle.systems/
