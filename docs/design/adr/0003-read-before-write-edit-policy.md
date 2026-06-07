# ADR 0003: Read-Before-Write Edit Policy

Status: accepted

## Context

An agent can accidentally overwrite code it has not inspected or code that
changed outside the session. This is especially risky in a shared workspace
where the user may edit files while the agent is running.

## Decision

Existing files must be fully read before `Edit` or `Write` can modify them. The
read records a JSON-compatible snapshot:

```text
version
mtime_ns
size
sha256
line_ending
partial_read
```

Writes are rejected when the file was only partially read or when the snapshot
does not match the current file.

## Alternatives

- Allow edits without prior reads.
- Trust mtime alone.
- Always ask the user to resolve possible conflicts manually.

## Consequences

- The agent cannot modify unseen existing content.
- External edits are detected before disk writes.
- The model sometimes needs an extra full `Read` before editing, but the safety
  behavior is visible and testable.

## Verification

- `tests/test_tools_runtime.py::test_edit_requires_prior_full_read`
- `tests/test_tools_runtime.py::test_edit_rejects_partial_read_snapshot`
- `tests/test_tools_runtime.py::test_edit_rejects_file_changed_since_read`
- `tests/test_tools_runtime.py::test_write_existing_file_requires_prior_read`
