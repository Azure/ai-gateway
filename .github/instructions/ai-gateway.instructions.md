---
applyTo: "src/ai-gateway/**"
---

# AI Gateway Azure CLI extension

For every change under `src/ai-gateway/`, determine whether it affects the
extension's commands, arguments, defaults, constraints, examples, or other
user-visible behavior. When it does, update `src/ai-gateway/README.md` in the
same change. Test-only changes, refactoring, formatting, and internal
implementation changes do not require a README edit when behavior is unchanged.

Follow the README's existing concise command-reference pattern:

- Organize commands by command group.
- List each command and its syntax in the group's command table.
- Add option tables and examples only when they clarify non-obvious behavior.
- Remove or revise documentation when behavior is removed or changed.
- Do not add generic prose, duplicate Azure CLI help, or document behavior that
  is not implemented.
