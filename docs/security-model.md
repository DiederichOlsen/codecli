# PyAgent Security Model

PyAgent's security goal is not to claim complete sandboxing. The goal is an
auditable local runtime: every sensitive tool call should have a structured
decision, a clear reason, and a replayable trace.

## Scope

PyAgent currently protects the local workspace through runtime policy checks:

- Tool calls pass through a fixed pipeline: parse, lookup, schema validation,
  permission decision, execution, and verification state update.
- Read-only tools are allowed conservatively.
- File edits and writes are restricted to the workspace and protected by
  read-before-write snapshots.
- Bash commands are classified before execution.
- Non-interactive sessions fail closed when a tool would require user approval.
- Runtime audit events are written as local JSONL files.

PyAgent does not currently provide an OS-level sandbox. Bash commands that are
approved still run as local subprocesses with the user's normal operating-system
permissions.

## Permission Decisions

Permission decisions are plain JSON-compatible data:

```text
behavior: allow | ask | deny
reason: human-readable explanation
policy: ExplicitRulePolicy | ModePolicy | FilePathPolicy | ToolPolicy | BashPolicy | InteractiveApprovalPolicy
classification: readonly | file_write | file_write_with_diff | dangerous | needs_confirmation | blocked_by_mode | ...
risk_tags: string[]
normalized_input: command, path, or rule target
matched_rule: optional permission rule
```

The human-readable reason is for the CLI. The other fields are for audit,
testing, and future Rust migration.

## Permission Order

The current permission flow is intentionally small:

1. Explicit deny and allow rules from `.pyagent/permissions.json`.
2. Permission mode checks such as `plan`, `accept_edits`, and `bypass`.
3. Tool-specific policies for file paths and Bash commands.
4. Interactive approval, or denial in non-interactive sessions.

Deny rules are evaluated before allow rules. Unmatched shell commands require
approval unless `bypass` mode applies. Dangerous shell commands still require
approval.

## File Safety

File paths must resolve inside the workspace. Paths containing sensitive
directories such as `.git`, `.claude`, and `.pyagent` are treated as unsafe.
Selected shell and credential configuration files are also treated as unsafe.

Existing files must be fully read before `Edit` or `Write` can modify them. A
partial read does not unlock editing. If a file changes after it was read, the
write is rejected until the file is read again.

The file snapshot contract is JSON-compatible:

```text
version
mtime_ns
size
sha256
line_ending
partial_read
```

This contract is meant to remain stable if the implementation later moves into
Rust.

## Bash Safety

`BashPolicy` is a conservative classifier, not a full shell parser. It records:

- behavior
- classification
- risk tags
- normalized command
- quote-aware command segments
- shell operators

Known read-only commands are allowed. Dangerous patterns such as recursive
delete, hard git reset, network download commands, generated-code execution,
PowerShell file writes, privilege elevation, and persistence mechanisms require
approval. Commands that cannot be confidently classified require approval in
default mode.

PowerShell is treated as a first-class shell surface. The policy includes
Windows-specific risk tags such as `windows_shell`, `policy_bypass`, and
`persistence`.

## Runtime Audit Trace

Tool execution emits local JSONL audit events under:

```text
.pyagent/audit/{session_id}.jsonl
```

Current event names:

```text
tool_call_received
args_parsed
tool_lookup
schema_validated
permission_decided
tool_started
tool_finished
verification_state_updated
```

Large text fields such as `content`, `old_string`, and `new_string` are not
stored directly in argument audit records. PyAgent stores their character count
and SHA-256 hash instead.

## Verification State

After `Edit`, `Write`, or verification-like `Bash` commands, PyAgent records a
verification state:

```text
not_required
unverified
passed
failed
```

This state is factual. It does not guess the correct command to run and does not
currently block final answers.

## Known Limits

- There is no OS-level filesystem or network sandbox yet.
- Bash parsing is conservative and incomplete.
- Symlink and Windows junction handling should become an explicit policy module.
- Network tools are classified only through command patterns.
- Audit logs are local files, not tamper-resistant records.
- Secrets redaction is limited to avoiding full storage of large edit content.

These limits are part of the security model. The project should prefer explicit
documented boundaries over vague safety claims.
