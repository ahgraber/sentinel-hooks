# Delta Spec: session-tool-checks

## MODIFIED Requirement: ToolRegistrationPattern

ADDED to existing spec:

The system SHALL define tool checks using `require_tool` and `recommend_tool` registration
functions that co-locate each tool's name and install hint as a single declaration.

```bash
require_tool()   { required_tools+=("$1" "$2"); }    # name, install_hint
recommend_tool() { recommended_tools+=("$1" "$2"); } # name, install_hint
```

Required tools SHALL be registered with `require_tool`.
Recommended tools SHALL be registered with `recommend_tool`.

All registered checks SHALL be evaluated by two loops at the bottom of the script —
one for required tools (exits 2 on missing) and one for recommended tools (warns, exits 0).

Repeated `if ! command -v <tool> >/dev/null` blocks are NOT permitted.
