---
description: Create an AI Gateway SKU in Azure API Management and verify that it is ready for configuration.
argument-hint: <gateway-name> <resource-group> <region> [optional requirements]
---

# /ai-gateway:create

Create an AI Gateway for an administrator or platform engineer. Follow the
prerequisites, target resolution, safety rules, and **Create a gateway** workflow
in `skills/manage-ai-gateway/SKILL.md`.

Use `$ARGUMENTS` for the gateway name, resource group, region, and any stated
requirements. Confirm missing or ambiguous values before execution. Check the
active Azure subscription and whether the gateway already exists; do not treat an
authorization error as “not found.” Show the proposed subscription, resource
group, name, region, and options before running `az ai-gateway create`.

After creation, verify with `az ai-gateway show`. Ask before changing Azure CLI
defaults. Stop after reporting the created gateway and its state; configure assets
only when the user explicitly requested them.
