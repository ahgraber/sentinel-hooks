# Delta for dangerous-bash-blocking

## REMOVED Requirements

### Requirement: ToolScope

Removed because: the hook evaluates the command of every call it receives, and each agent's registration selects which calls reach it.
A `tool_name` test inside the hook spelled the shell tool a second time, beside the declared vocabulary, and held only for the agents that spell it `Bash`.
