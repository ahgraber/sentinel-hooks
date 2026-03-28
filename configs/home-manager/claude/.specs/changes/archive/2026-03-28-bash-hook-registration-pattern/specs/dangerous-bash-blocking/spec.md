# Delta Spec: dangerous-bash-blocking

## MODIFIED Requirement: RuleRegistrationPattern

ADDED to existing spec:

The system SHALL define all pattern-based blocking rules using a `rule` registration function
that co-locates each rule's exemption type, pattern, and block message as a single declaration.

```bash
rule() {
  rules+=("$1" "$2" "$3")  # exemption, pattern, message
}
```

Message strings that are shared across multiple rules within the same threat category SHALL be
extracted into named variables (e.g. `_MSG_REVERSE_SHELL`) to avoid repetition.

All registered rules SHALL be evaluated by a single loop at the bottom of the script, replacing per-category loops.

This ensures that adding, removing, or reordering any rule is an atomic edit.
Separate per-category arrays with individual loops are NOT permitted.
