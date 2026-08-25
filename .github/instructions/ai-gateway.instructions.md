---
applyTo: "src/ai-gateway/**"
---

# AI Gateway Azure CLI extension

For every change under `src/ai-gateway/`, determine whether users need new
information to invoke a command correctly or interpret its result. When they
do, update `src/ai-gateway/README.md` in the same change. Do not update the
README merely because behavior is user-visible. Routine feedback such as
progress indicators, acceptance or completion messages, and stderr routing
does not need documentation unless it introduces a user choice or an
unexpected constraint.

Follow the README's existing concise command-reference pattern:

- Organize commands by command group.
- List each command and its syntax in the group's command table.
- Add option tables and examples only when they clarify non-obvious behavior.
- Prefer updating an existing command, option, constraint, or example over
  adding prose.
- State requirements and constraints directly. Do not explain implementation
  choices, design rationale, or why the CLI behaves a certain way.
- Do not add release-note-style descriptions of a change.
- Remove or revise documentation when behavior is removed or changed.
- Do not add generic prose, duplicate Azure CLI help, or document behavior that
  is not implemented.
