[AI Gateway labs](README.md) › Troubleshooting <!-- gh -->

# Troubleshooting

The errors you might hit in the labs, with their likely causes and fixes. Errors from setting up and deploying, such
as a missing extension or an unavailable region, are under [Setup and deployment](#setup-and-deployment), and the
others are under their lab. Look for the error code or the message, for example `429` or `ValidationError`.

**Jump to:** [Setup and deployment](#setup-and-deployment) · [Quick start](#quick-start) · [00](#lab-00-how-ai-gateway-works) · [01](#lab-01-provision-a-gateway) · [02](#lab-02-first-model-call) · [03](#lab-03-multi-provider-aliases) · [04](#lab-04-federate-mcp-tools) · [05](#lab-05-tool-allow-and-block-lists) · [06](#lab-06-token-limits) · [07](#lab-07-cost-budgets) · [08](#lab-08-content-safety) · [09](#lab-09-gateway-wide-baselines) · [10](#lab-10-runtime-api-keys) · [11](#lab-11-entra-id-and-rbac) · [12](#lab-12-backend-identities) · [13](#lab-13-monitoring) · [14](#lab-14-opentelemetry-chargeback) · [15](#lab-15-agent-frameworks) · [16](#lab-16-foundry-hosted-agent) · [17](#lab-17-coding-agent-plugin) · [18](#lab-18-private-networking) · [19](#lab-19-tool-threat-protection) · [20](#lab-20-agent-365-governance) · [21](#lab-21-enterprise-reference) · [22](#lab-22-priority-and-weighted-routing) · [23](#lab-23-streaming-responses) · [24](#lab-24-github-copilot-byok) <!-- gh -->

## Setup and deployment

Setup guide: [The one-time tasks that every lab builds on](SETUP.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `'aigateway' is misspelled or not recognized by the system` | The `aigateway` extension isn't installed | [Install the extension](SETUP.md#install-the-aigateway-extension), then run `az aigateway version`. |
| `MissingSubscriptionRegistration`, or `The subscription is not registered to use namespace` | A resource provider isn't registered in the subscription | [Register the resource providers](SETUP.md#register-the-resource-providers), or ask your subscription administrator. |
| `LocationNotAvailableForResourceType` | The location isn't a region where AI Gateway is available | Pick a region from [Find the available regions](SETUP.md#find-the-available-regions). |
| `RequestDisallowedByAzure`: `The selected region is currently not accepting new customers` | The region has AI Gateway, but your subscription can't create new resources there | Pick another region from the list. |
| `InvalidResourceGroupLocation` from `azd up` | The resource group `rg-<environment name>` already exists in another region | Run `azd env new` with a new environment name, or delete the old resource group. |
| Your subscription is disabled in the portal's subscription picker | You lack write permission for API Management or connector gateways in that subscription | Ask for **Contributor** on the subscription or resource group, or pick another subscription. |

## Quick start

Quick start: [Your first model call in 5 minutes](quickstart/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| A subscription is disabled in **Create AI gateway** | You can't write API Management or connector gateway resources in it | Pick another subscription, or ask for **Contributor** on it. |
| `AuthorizationFailed` on `Microsoft.Authorization/roleAssignments` | You can create resources but not role assignments | Ask for **Owner**, or **Role Based Access Control Administrator**, on the resource group. |
| `LocationNotAvailableForResourceType` | AI Gateway isn't available in the region | Pick a region from [Find the available regions](SETUP.md#find-the-available-regions). |
| `RequestDisallowedByAzure`: `The selected region is currently not accepting new customers` | The region has AI Gateway, but your subscription can't create new resources there | Pick another region from the list. |
| `InvalidResourceProperties`: `The specified SKU 'GlobalStandard' for model 'gpt-6-luna 2026-09-22' is not supported in this region` | `gpt-6-luna` isn't available in the region | Pick a region where the model check in [Find the available regions](SETUP.md#find-the-available-regions) prints `GlobalStandard`. |
| `InsufficientQuota` on the model deployment | The subscription has no `gpt-6-luna` capacity left in the region | Start again in another region: set `LOCATION` in the Azure CLI track, or run `azd env new` with a new name and another `--location` in the Bicep + azd track. Or free capacity in [Foundry](https://ai.azure.com). |
| `InvalidResourceGroupLocation` from `azd up` | The resource group `rg-<environment name>` already exists in another region | Run `azd env new` with a new environment name, or delete the old resource group. |
| `403` or `404` from the gateway in the first minute | The gateway's role on the Foundry account, or the new alias, is still taking effect | Wait a minute and call again. |
| `403` from the backend that doesn't go away | The gateway's managed identity has no role on the Foundry account | Assign it **Foundry User** on the account, as in the Azure CLI track's **Deploy the model in Foundry** step, and wait a few minutes. |
| `401` | The key is missing, wrong, or in the wrong header | Send it in the `api-key` header, or as `Authorization: Bearer <key>`. In the portal, copy it again from **Access** › **Keys**. |
| `400` that mentions authentication | The request has both an `api-key` and an `Authorization` header | Send only one of them. |
| `The subscription is not registered to use namespace` | A resource provider isn't registered yet | Run the `az provider register` loop from **Start creating the gateway**, then try again. |

## Lab 00: How AI Gateway works

Lab 00: [How Azure AI Gateway works](00-how-ai-gateway-works/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| A model call says the model can't be found | The `model` field doesn't match an alias | Copy the alias from **Models**, or from the code sample in **Catalog** |
| An Anthropic call fails on the OpenAI endpoint | The gateway doesn't translate between protocols | Call `/default/models/anthropic/v1/messages` with `anthropic-version: 2023-06-01` |
| You can't create a gateway in your region | AI Gateway isn't available there yet | Pick a region from [Find the available regions](SETUP.md#find-the-available-regions) |
| Monitoring is empty | No telemetry destination | Connect Application Insights in **Monitoring** › **Settings** |

## Lab 01: Provision a gateway

Lab 01: [Provision your AI Gateway](01-provision-gateway/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| Your subscription is disabled in the portal's subscription picker | You lack write permission for API Management or connector gateways in that subscription | Ask for **Contributor** on the subscription or resource group, or pick another subscription. |
| `LocationNotAvailableForResourceType` | `$LOCATION` or the template's `location` isn't a region where AI Gateway is available | Pick a region from [Find the available regions](SETUP.md#find-the-available-regions). The template defaults to `eastus2`. |
| `RequestDisallowedByAzure`: `The selected region is currently not accepting new customers` | The region has AI Gateway, but your subscription can't create new resources there | Pick another region from the list. |
| The name is rejected | Gateway names are globally unique and limited to 24 characters: letters, digits, and hyphens, starting with a letter | Pick another name that follows the rules. |
| `AIGatewaySubscriptionGatewayLimitExceeded`: `…has reached the maximum of 5 AI Gateway resources allowed in this region.` | The subscription already has five gateways in `$LOCATION` | Delete a gateway you no longer need, or create this one in another available region. |
| `InvalidSkuName`: `Supported AI Gateway SKU names are 'Premium' and 'Consumption'.` | Your template sets another `sku.name`, such as `AIGateway` from older samples | Set `sku: { name: 'Consumption' }`, as [`infra/gateway.bicep`](01-provision-gateway/infra/gateway.bicep) does. |
| `MissingSubscriptionRegistration` | A resource provider isn't registered in the subscription | [Register the resource providers](SETUP.md#register-the-resource-providers), or ask your subscription administrator. |
| `Could not resolve host` when you call the URL | Provisioning or DNS isn't finished | Run `az aigateway wait -g "$RG" -n "$GATEWAY" --created` and retry. |
| `'aigateway' is misspelled or not recognized by the system` | The `aigateway` extension isn't installed | [Install the `aigateway` extension](SETUP.md#install-the-aigateway-extension), then run `az aigateway version`. |

## Lab 02: First model call

Lab 02: [Publish a Foundry model and make your first call](02-first-model-call/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` from the gateway | The key is missing, misspelled, or deleted | Send an active runtime key in the `api-key` header or as the SDK API key. Create a new key if you lost the value. |
| `400` with `Specify either an API key or an Authorization header, not both` | The client sends an `api-key` header and an `Authorization` header, such as an SDK placeholder key | Pass the runtime key as the SDK API key and remove the `api-key` default header. |
| `403` mentioning permissions on the Foundry account | The gateway's identity lacks **Foundry User**, or the assignment hasn't propagated yet | Wait a few minutes. If it persists, assign the role as shown in the portal track. |
| `404` with `model_not_found` | `model` doesn't match an alias exactly | Copy the alias from the model's **Aliases** tab or from **Catalog**. |
| `400` `unsupported_parameter` for `max_tokens` or `temperature` | `gpt-6-luna` is a reasoning model | Send `max_completion_tokens` instead of `max_tokens`. Set `temperature` only together with `reasoning_effort: "none"`. |
| `200` with empty `content` and `finish_reason` `length` | Reasoning used the whole `max_completion_tokens` budget | Raise the budget, or send `reasoning_effort: "none"` for short, direct replies. |
| The Responses API call fails while Chat Completions works | The model doesn't advertise the Responses interface | Check the supported interfaces on the model details page and call only those. |
| The import wizard doesn't list your account | It's already imported into this gateway, or you can't read it in that subscription | Check **Models** for an existing provider, or ask for read access to the account. |
| `AuthorizationFailed` on `roleAssignments` during deployment | You can't create role assignments on the Foundry account | Ask for **Role Based Access Control Administrator** on the account, or have an owner grant the role. |

## Lab 03: Multi-provider aliases

Lab 03: [Publish models from any provider behind stable aliases](03-multi-provider-aliases/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| The wizard discovers no models, or times out | The base endpoint URL includes `/v1`, the header name is wrong, or the provider doesn't serve `/v1/models` | Use `https://api.anthropic.com` and `x-api-key`. If the provider can't list models, add them with **Individual model**. |
| `401` from the gateway | The `api-key` header is missing or holds the Anthropic key instead of a gateway runtime key | Send a runtime key from **Access** › **Keys** in the `api-key` header. |
| An authentication error from Anthropic in the response body | The stored provider key is wrong or expired, or **Include Bearer** is selected for Anthropic | Update the provider's API key and clear **Authentication scheme**. |
| `400` that mentions `anthropic-version` | The request doesn't send the `anthropic-version` header | Add `anthropic-version: 2023-06-01`. |
| `404` or a "model not found" error | The `model` value doesn't exactly match an alias, or you called the OpenAI route for an Anthropic model | Copy the alias from **Models**, and call `/default/models/anthropic/v1/messages`. |
| "Callable aliases must be unique" | Another alias in the gateway already uses that name | Pick a different alias, or retarget the existing one. |

## Lab 04: Federate MCP tools

Lab 04: [Federate MCP tools behind one endpoint](04-federate-mcp-tools/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` from the MCP endpoint | The key is missing, revoked, or sent in the wrong header | Send a runtime key from **Access** › **Keys** in the `api-key` header. |
| `404` from the MCP endpoint | Wrong server name in the URL, or the server is still provisioning | List the servers with `az aigateway mcp list -g "$RG" --gateway-name "$GATEWAY" -o table` and use the exact name in `/default/toolservers/<server-name>/mcp`. |
| `406` or an error about the `Accept` header | The client doesn't accept both JSON and SSE | Send `Accept: application/json, text/event-stream`, or use an MCP SDK. |
| `tools/list` returns an empty `tools` array | The registration is reachable but no backend returned tools | Check each backend's URL with `az aigateway mcp source list -g "$RG" --gateway-name "$GATEWAY" -n <server-name> -o table`, and check its authentication. |
| The whole server fails when one backend is down | That backend is **Required** | Turn **Required** off for backends that are nice-to-have, or fix the backend. |
| Backends or policies disappeared after a Bicep deployment | A Bicep deployment sends a `PUT`, which replaces an existing registration with the same name | Change existing servers with `az aigateway mcp update` or `az aigateway mcp source add` and `remove`, as in the CLI track, or deploy to a new name. |
| `mcp create` fails with "This MCP registration already exists; use mcp update." | A server with that name already exists | Change it with `az aigateway mcp update` or the `mcp source` commands, or choose another name. |
| `mcp source remove` fails with "Cannot remove the last source." | An MCP server needs at least one backend | Keep at least one backend, or delete the server with `az aigateway mcp delete`. |
| `400` with `Unsupported MCP-Protocol-Version` | The client sent an `MCP-Protocol-Version` header that isn't in **Supported MCP versions** | Add the version to the list if every backend supports it, or let the client negotiate a listed version. |
| `404` with "Federation tools/list failed: required endpoint '…' returned error: Backend selected protocol version '…' instead of '…'" | **Supported MCP versions** includes a version that this backend doesn't support, and the client negotiated it | Keep only versions that every backend supports. In the portal, edit and save each backend to recheck it. |
| `400` with JSON-RPC error `-32603`, "The request cannot be completed using the requested protocol version." | A `2026-07-28` request reached a backend that doesn't support `2026-07-28` | Remove `2026-07-28` from **Supported MCP versions** until every backend supports it. |
| `400` with JSON-RPC error `-32602`, "Required MCP request metadata is missing or malformed." | A `2026-07-28` request lacks the `Mcp-Method` or `Mcp-Name` header, or `params._meta` | Use an MCP SDK that implements `2026-07-28` instead of hand-written requests. |
| The portal shows "Backend isn't compatible with all configured MCP versions." | The backend doesn't report support for every selected version | Return to **Basic info** and change **Supported MCP versions**, or update the backend. |
| Creating a server fails with `502 Bad Gateway`, or a Bicep deployment keeps running | Another MCP server in the gateway already uses the same display name | Choose a unique display name, for example with the Bicep `displayName` parameter. |

## Lab 05: Tool allow and block lists

Lab 05: [Control which tools agents can call](05-mcp-tool-controls/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| A tool you blocked still appears in `tools/list` | Expected. Blocked tools remain visible, but the gateway blocks their execution | Call the tool to confirm that it's blocked. To hide a tool, leave it out of the allow list instead. |
| `tools/list` returns no tools | The allow list matches nothing | Check the patterns against the exact tool names. |
| `initialize` returns `AccessBlockedByGateway` | The server access is **Blocked** | Set **MCP server access** to **Active**, or run `azd env set MCP_SERVER_ACCESS active` and `azd provision`. |
| An allowed tool is blocked | A blocked pattern also matches it. Blocked patterns take precedence | Make the blocked pattern narrower, for example `*code_sample*` instead of `*sample*`. |
| `429` on the first request of a run | The previous step used up the window, or a **Gateway** scope rate limit also applies | Wait for `Retry-After`, and review **Policies** for every limit that covers the MCP server. |
| Never `429` | The policy is on another asset, it was saved moments ago, or the burst spans two windows | Check the policy's scope, wait a minute after you save it, and run a longer burst, for example `./infra/trigger-request-rate.sh learn 12`. |
| Other policies vanished after `mcp update` | `--policies` replaces the whole `policies` array | Always read the current array, merge, then update, as shown in the Azure CLI track. |
| Tool rules or policies set in the portal vanished after `azd provision` | A Bicep deployment sends a `PUT`, which replaces the whole MCP server | Change the azd environment values and run `azd provision` instead of editing the server in the portal. |

## Lab 06: Token limits

Lab 06: [Throttle tokens per caller with token limits](06-token-limits/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| Every request returns `200`, never `429` | The limit is on a different model or alias than the one you call, or the window reset between requests | Check that the request `model` matches an alias of the limited model. Run the burst without pauses. |
| `429` on the very first request | Another token limit with a lower allowance applies, for example a **Gateway** scope policy, or the counter is shared because **Counter dimensions** is empty | Review **Policies** for every limit that covers the model. Pick **Caller identity** for per-caller counters. |
| `403` with `LlmCostQuotaExceeded` | A **Cost limit** blocked the call, not the token limit | See [Enforce cost budgets](07-cost-budgets/README.md). |
| `429` without a gateway token limit | The backend deployment ran out of TPM | Raise the deployment's capacity in Foundry, or lower per-caller gateway limits so their sum fits. |
| Other policies vanished after the REST call | `PATCH` replaces the whole `policies` array | Always `GET`, merge, then `PATCH`, as shown in the REST track. |
| `ValidationError` with target `counterKey` | `counterKey` is a string such as `"Identity"`, uses another value, or is missing | Send an array with `identity`, `ipAddress`, or both, for example `"counterKey": ["identity"]`. |

## Lab 07: Cost budgets

Lab 07: [Enforce cost budgets with per-caller overrides](07-cost-budgets/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| Every request returns `200`, never `403` | The cost limit is on a different model than the alias you call, your key has an override, or the model is so cheap that the calls haven't reached the budget | Check **Applies to** on the policy details page, use a key without an override, and lower the budget to `0.001` or send more requests. |
| `403` with `LLM cost quota is exceeded` on the first request | The key already spent more than the new amount in this period (spend is kept when you edit), or a **Gateway** scope cost limit is exhausted | Review every **Cost limit** in **Policies**. Raise the amount, or wait for the next renewal period. |
| An Entra override doesn't apply | An earlier override matched first, the caller used an API key, or you entered a service principal's application ID | Remove the earlier override and add them again in the order you want. Call with an Entra token. Use the service principal's **object ID**. |
| **Caller IP address** can't be selected in **Counter dimensions** | The policy has overrides | Remove all overrides, or keep **Caller identity**. |
| `429` instead of `403` | A **Token rate limit** or **Request rate limit** blocked the call, or the backend ran out of capacity | See [Throttle tokens per caller with token limits](06-token-limits/README.md). |
| Other policies vanished after the REST call | `PATCH` replaces the whole `policies` array | Always `GET`, merge, then `PATCH`, as shown in the REST track. |
| `ValidationError` with target `counterKey` | `counterKey` is a string such as `"Identity"`, or it's missing | Send an array, for example `"counterKey": ["identity"]`. A cost limit always needs `counterKey`. |

## Lab 08: Content safety

Lab 08: [Screen prompts and responses with content safety](08-content-safety/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| Ordinary prompts return `400` | A threshold is too strict for your traffic, or another content safety policy, such as a **Gateway** scope policy, also applies | Review **Policies** for every content safety policy that covers the model. Move categories from **Strict** to **Balanced** and retest with representative prompts. |
| Nothing is ever blocked | The policy is on a different model or alias than the one you call, or a category is **Off** | Check the policy's scope and that the request `model` matches an alias of that model. |
| `400` that mentions `content_filter`, or `finish_reason` is `content_filter` | The Foundry deployment's **Content filter** acted, not the gateway | Review the deployment's content filter in Foundry. The gateway policy is managed separately. |
| `400` that isn't about content | The request itself is invalid, for example an unknown model alias | Read the error message, and check the request body and the alias. |
| `ValidationError` such as `contentSafety.violenceSeverity must be one of: Low, Medium, High, None.` | A severity uses a portal label such as `Strict` or `Balanced` | Use the API values from the table in [How it works](08-content-safety/README.md#how-it-works): `Low`, `Medium`, `High`, or `None`. |
| Other policies vanished after the `PATCH` | `PATCH` replaces the whole `policies` array | Always `GET`, merge, then `PATCH`, as shown in the CLI and REST tracks. |

## Lab 09: Gateway-wide baselines

Lab 09: [Set gateway-wide policy baselines](09-gateway-baselines/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| Every call returns `403` | Your public IP address changed (new network, VPN, or hotspot), or your network reaches the gateway from a different address than the one `api.ipify.org` reported | Check `curl -s https://api.ipify.org` again and update the IP filter. If you use a proxy or split-tunnel VPN, ask your network team for the egress ranges. Management calls still work, so you can always fix the list. |
| Teammates, pipelines, or hosted agents get `403` | Their egress addresses aren't on the allow list | Add their CIDR ranges, or remove the IP filter until you know them. |
| Ordinary prompts return `400` | Content safety blocked them, from the baseline or from a stricter asset policy | Review every **Content safety** policy that covers the asset in **Policies**, and retest with representative prompts. |
| `429` much earlier than the baseline allows | A tighter token or request rate limit on the model, alias, or MCP server applies | Review **Policies** for every limit that covers the asset. The lowest applicable limit wins. |
| The `PATCH` returns a validation error about `counterKey` or `scope` | `counterKey` is a string such as `"Identity"` instead of an array, or the shape differs from what the API version expects | Use `"counterKey": ["identity"]`. If it still fails, create that policy once in the portal at **Gateway** scope, read the shape with the `GET`, and use it in your script or policy file. |
| `Set ALLOWED_CIDRS ...` or `Use CIDR notation ...` from the script | `ALLOWED_CIDRS` is empty, or an entry has no prefix length | Set it to comma-separated CIDR ranges, for example `"$MY_IP/32"`. |
| Other Gateway scope policies vanished after the REST call | `PATCH` replaces the whole `policies` array | Always `GET`, merge, then `PATCH`, as shown in the REST track and the script. |
| `jq: command not found` | `jq` isn't installed | Install `jq`, or use the PowerShell commands. |

## Lab 10: Runtime API keys

Lab 10: [Issue and rotate runtime API keys](10-api-keys/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| A new key gets `401` | The value has a space or line break, or an MCP client sends it in `Authorization` instead of `api-key` | Copy the value again and send it as `api-key: <value>`. |
| `400` with `Specify either an API key or an Authorization header, not both` | The client sends an `api-key` header and an `Authorization` header | Send one of them. With an OpenAI SDK, pass the key as the SDK's API key and remove the extra header. |
| `401` right after **Rotate key** in the portal | Portal rotation replaces the primary value immediately | Give the client the value from **API key rotated successfully**. Next time, use the CLI secondary-value flow. |
| "The key was created, but its value couldn't be retrieved." | You don't have `Microsoft.ApiManagement/aigateways/apiKeys/listSecrets/action` | Use **Rotate key** to get a new value, or ask someone with that permission, such as a Contributor, to read it. |
| `check-key` prints `not checked` with `HTTP 404` | The gateway doesn't know the alias in `AI_GATEWAY_MODEL`, so it never checked the key | Set `AI_GATEWAY_MODEL` to an alias from **Models**, for example the one from lab 02. |
| A key that worked gets `401`, and nobody rotated it | The key is `suspended` | Check `state` with the list command, and set it back to `active` if the suspension is over. |
| `check-key` prints `key accepted, but the call failed` | The key works, but `AI_GATEWAY_MODEL` isn't an alias you can call, or a policy blocked the request | Set `AI_GATEWAY_MODEL` to an alias from **Models**, for example the one from lab 02. |
| `Forbidden` from `az keyvault secret set` or `secret show` | You have no data-plane role on the vault, or the role assignment hasn't applied yet | Assign **Key Vault Secrets Officer** on the vault and wait a few minutes. |
| Monitoring shows no caller identities | Monitoring isn't configured, or the time range has no traffic | Complete [Monitor usage, cost, and traces](13-monitoring/README.md), send requests with each key, and widen the time range. |

## Lab 11: Entra ID and RBAC

Lab 11: [Go keyless with Microsoft Entra ID and RBAC](11-entra-rbac/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` on every Entra call | The token is expired, or it was issued for another audience, such as Azure Resource Manager | Request a new token for `https://azure-api.net/aigateway` (`.default` for app-only callers). Check `aud` in the decoded token. |
| `403` right after you assigned the role | Role assignments take several minutes to apply | Wait and retry with a fresh token. In the playground, use **Back to playground** after reviewing access. |
| `403` for one model or MCP server only | The role is scoped to a different alias or MCP server, or the role doesn't cover it (Models User on an MCP server, Tools User on a model) | Assign a compatible role at the gateway or at that alias or MCP server. |
| `403` even though the role is correct | A gateway policy (for example a cost limit), the request proxy, or the backend rejected the call | Read the error code in the response body before changing permissions. `LlmCostQuotaExceeded` comes from a cost limit. |
| `AuthorizationFailed` when you create the assignment | You have **Contributor**, which can't write role assignments | Ask an **Owner**, **User Access Administrator**, or **Role Based Access Control Administrator** to assign the role. |
| `DefaultAzureCredential failed to retrieve a token` | No sign-in is available to the credential chain | Run `az login`, or sign in to the Azure extension in your IDE, then rerun the sample. |

## Lab 12: Backend identities

Lab 12: [Call backends with managed identities](12-backend-identity/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `403` mentioning permissions on the Foundry account right after the switch | The role assignment hasn't propagated, or it's at a different scope than the Foundry account | Wait a few minutes. Check `az role assignment list --assignee "$IDENTITY_PRINCIPAL_ID" --scope "$FOUNDRY_ID" -o table`. |
| Calls fail after the switch and the role is in place | `clientId` holds the principal (object) ID, or the identity isn't attached to the gateway | Use the identity's **Client ID**, and check that `az aigateway identity show -g "$RG" -n "$GATEWAY" --query userAssignedIdentities` lists the identity. |
| `az aigateway identity assign` fails with an authorization error | You can't assign that identity to resources | Ask for **Managed Identity Operator** on the identity. |
| `az aigateway identity show` reports that no identity is assigned to the gateway | The gateway has no managed identity | Enable it with `az aigateway identity assign` in [Check the system-assigned identity](12-backend-identity/README.md#check-the-system-assigned-identity), then grant it **Foundry User**. |
| Calls fail after you detach an identity or disable the system identity | An asset still uses that identity | Check **View access** › **Backend access** before you remove an identity, and switch those assets first. |
| `AuthorizationFailed` on `roleAssignments` | You can't create role assignments on the Foundry account | Ask for **Role Based Access Control Administrator** on the account, or have an owner grant the role. |

## Lab 13: Monitoring

Lab 13: [Monitor usage, cost, and traces](13-monitoring/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| "Enable all telemetry signals" on the dashboard | Metrics, logs, or traces is turned off | Select **Open Monitoring settings** and set all three endpoints, or disable monitoring and configure it again with Application Insights. |
| "This legacy exporter no longer activates OTLP signals" in **Settings** | The exporter has kind `applicationInsights`, for example from the sample's Bicep or a setup before 2026-08-28 | Select **Settings** › **General** › **Disable monitoring**, then **Configure telemetry** again with the same Application Insights resource. |
| **Assign Monitoring Metrics Publisher role** fails | You can't create role assignments on the destination | Ask an **Owner** to grant the role on the Data Collection Rule, or to run the setup. |
| **Discover OTLP endpoints** fails with "Could not resolve the Data Collection Rule" | OTLP support was just enabled and Azure is still provisioning it | Wait a few minutes, then select **Retry**. |
| "Model token and estimated cost data are incomplete until you add a Prometheus access token" | The portal can't read the metrics workspace with your session | Paste a token from `az account get-access-token --resource https://prometheus.monitor.azure.com --query accessToken -o tsv` into **Prometheus access token**. |
| Dashboard and queries are empty | No traffic in the selected range, or ingestion is still catching up | Widen the time range, wait a few minutes, and run the traffic script again. |

## Lab 14: OpenTelemetry chargeback

Lab 14: [Attribute tokens and cost with OpenTelemetry](14-otel-chargeback/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| No **Token claim attributes** section in **Settings** | The exporter is the legacy `applicationInsights` kind | Disable monitoring and configure it again, as in [Monitor usage, cost, and traces](13-monitoring/README.md). |
| The `entra` rows return `401` or `403` | Wrong token audience, or no **AI Gateway Models User** role yet | Get the token for `https://azure-api.net/aigateway`, check the role assignment, wait a few minutes, and get a new token. |
| Entra callers show as **Unattributed** on **Models** | `tid` or `oid` isn't exported to **Metrics** | Select **Metrics** for both and send new traffic. Earlier requests stay unattributed. |
| The chargeback query returns no rows | Telemetry hasn't arrived, the **Logs** signal is off, or your API reports usage under other names | Wait a few minutes, then run `OTelLogs \| where TimeGenerated > ago(1h) \| take 5` and compare the `Attributes` with the query. |
| `Tenant` or `ClientApp` is empty for Entra rows | The claim wasn't exported to **Logs** when the request ran | Enable **Logs** for the claim and send new traffic. |
| The Prometheus query returns `401` or `403` | Your account can't read the Azure Monitor workspace | Ask for a data read role on the Azure Monitor workspace, such as **Monitoring Data Reader**, then get a new token. |

## Lab 15: Agent frameworks

Lab 15: [Connect agent frameworks to models and tools](15-agent-frameworks/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` from the model or MCP endpoint | The key is missing, wrong, or revoked, or the header isn't sent | Check `AI_GATEWAY_API_KEY` in `.env` and that the key exists under **Access** › **Keys**. A value set in your shell overrides `.env`. |
| `404` from the MCP endpoint | `AI_GATEWAY_MCP_SERVER` doesn't match an MCP server name | Copy the name from **MCP servers**, or the endpoint from the server's page. |
| A `4xx` error that mentions the model | `AI_GATEWAY_MODEL` isn't a callable alias | Copy the alias exactly from the model's **Aliases** tab. |
| The agent answers without citing any URL | The MCP server publishes no tools, or tool controls block them | Run `list_tools.py` from [Federate MCP tools behind one endpoint](04-federate-mcp-tools/README.md) and check the server's tool controls. |
| `429` responses | A token limit or rate limit on the alias, MCP server, or gateway | Expected when a policy applies. Wait for `Retry-After`, or raise the limit. |
| `ModuleNotFoundError` | The virtual environment isn't active | Activate `.venv` and run `pip install -r requirements.txt` again. |

## Lab 16: Foundry hosted agent

Lab 16: [Deploy a Foundry hosted agent behind AI Gateway](16-foundry-hosted-agent/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `400` "Specify either an API key or an Authorization header, not both" | The code sends the key as the SDK's API key and also in an `api-key` header | Pass the key only as the SDK's `api_key`, and remove the `api-key` default header from the model client. |
| `401` from the MCP endpoint | The key went in `Authorization: Bearer` | The MCP endpoint takes keys only in the `api-key` header, as in `main.py`. |
| `401` from the model endpoint | The key is wrong, suspended, or deleted | Check `hosted-agent` in **Access** › **Keys**, load the value again, run `azd env set AI_GATEWAY_API_KEY`, then `azd deploy`. |
| `404` from the model endpoint | `AI_GATEWAY_MODEL` doesn't match an alias | Copy the alias exactly from the model's **Aliases** tab, run `azd env set AI_GATEWAY_MODEL`, then `azd deploy`. |
| `429` "Token limit is exceeded" | A token limit on the alias, such as the one from this lab | Wait for the time in the message, or remove the policy. |
| `429` from tool calls | A request rate limit on the `learn` server, for example from [Control which tools agents can call](05-mcp-tool-controls/README.md) | Wait for the `Retry-After` time, or remove the policy from the MCP server. |
| `RuntimeError: Set AI_GATEWAY_URL` | An azd environment value is missing | Run `azd env set` for the missing value, then `azd ai agent run` or `azd deploy`. |
| The hosted agent still uses an old value | Foundry reads environment variables when the agent version is created | Run `azd deploy` after every `azd env set`. |
| `[CodeError] [tool.poetry] section not found` during deployment | A `pyproject.toml` without a lock file was added to `src/gateway-agent` | Keep `requirements.txt` as the dependency file, or commit a `uv.lock` next to `pyproject.toml`. |
| `azd ai agent run` can't download packages, with a certificate error | A proxy on your network inspects TLS traffic | Set `UV_SYSTEM_CERTS=true` (`UV_NATIVE_TLS=true` in older uv versions) so uv trusts your system certificates, then run it again. |

## Lab 17: Coding-agent plugin

Lab 17: [Build on your gateway with coding agents](17-coding-agent-plugin/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `/ai-gateway:discover` isn't recognized | The plugin isn't installed or the client hasn't reloaded it | Repeat the install for your agent, then restart it. Check with `copilot plugin list` in GitHub Copilot CLI or `gemini extensions list` in Gemini CLI. |
| The plugin can't list models, or Azure returns `401` or `403` | `az` is signed in to another tenant or subscription, or your account can't read the gateway | Run `az account show`, then `az account set --subscription <subscription-id>`. Ask for read access to the gateway. |
| The plugin stops at the credential step | Your account can't list key secrets on the gateway | Create or get a key as in **Before you begin**, and tell the agent to read it from `AI_GATEWAY_API_KEY`. |
| `404 Resource not found` from the gateway | The URL is missing the `/default/` segment | Use `<gateway URL>/default/models/openai/v1` or `<gateway URL>/default/toolservers/<name>/mcp`. |
| `unknown_model` | The model name isn't one the gateway publishes, the client uses another protocol than the model supports, or a GitHub Copilot SDK older than 1.0.0 drops the key header | Use the name that discover reported or your alias. Pin `github-copilot-sdk>=1.0.0`. |
| `401` from the gateway | The key is missing or deleted, or an MCP call sends it as a bearer token. The MCP endpoint reads keys only from the `api-key` header. | Send the key in the `api-key` header. Create a new key if you deleted it. |
| `400` "Specify either an API key or an Authorization header, not both" | The client sends the key in `api-key` and also an `Authorization` header, as SDKs do when you pass a placeholder key | Send only one. For the model endpoint, pass the runtime key as the SDK's API key and drop the extra `api-key` header. |
| `KeyError: 'AI_GATEWAY_API_KEY'` | `.env` wasn't loaded, often because PowerShell saved it with a byte order mark | Export the variable in your shell, or save `.env` as UTF-8 without a byte order mark. |
| `429` | A token limit or the backend's quota | The wiring works. See [Throttle tokens per caller with token limits](06-token-limits/README.md). |
| A tool server shows `0` tools | The server exposes no tools, or tool availability hides them | Check the server's tools in the portal, or see [Federate MCP tools behind one endpoint](04-federate-mcp-tools/README.md). |

## Lab 18: Private networking

Lab 18: [Lock down backend traffic with private networking](18-private-networking/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| The create dialog flags the subnet, or the create request fails with a subnet error | The subnet is in another subscription or region, smaller than `/27`, not delegated to `Microsoft.App/environments`, used by another gateway or resource, or its NSG lacks the 443 rules | Fix each item. The NSG needs outbound TCP 443 allow rules to the `Storage` and `AzureKeyVault` service tags. |
| The create request fails with `AIGatewaySubnetNotDelegated`: "Virtual network integration with subnet ID '…' requires the subnet to be delegated to 'Microsoft.App/environments'." | The subnet isn't delegated, or it's delegated to another service, such as `Microsoft.Web/serverFarms` | Delegate the subnet to `Microsoft.App/environments`, then create the gateway again. |
| The portal's subnet check shows a warning: "Subnet delegated to Microsoft.Web/serverFarms" | The portal check still expects the old delegation | Expected. Keep `Microsoft.App/environments` and continue. |
| "Virtual network integration for Azure AI Gateway can only be configured during creation." | You tried to add, change, or remove private routing on an existing gateway | Create a new gateway with private routing. |
| Model calls through the new gateway fail after you turn off Foundry public access | The gateway resolves Foundry to its public IP: the zones aren't linked to the integrated virtual network, the private endpoint has no DNS zone group, or the gateway was created without private routing | Check the `A` records and zone links, and confirm that `properties.backend.subnet.id` points to the integration subnet. |
| The gateway from the earlier labs, or another app, now gets `403` from Foundry | It reaches Foundry over the internet, and Foundry's public access is disabled | Expected. Use a dedicated Foundry resource for this lab, or re-enable public access when you finish. |
| The first call after the import returns `401` or `403` from the backend | The **Foundry User** role assignment hasn't propagated yet | Wait a few minutes, and confirm that the role is assigned to the new gateway's principal ID on the Foundry resource. |
| **Public network access** › **Disabled** is greyed out, or a `PATCH` to `Disabled` doesn't stick | Private frontend access isn't available for AI Gateway yet | Expected. Protect the public endpoint with keys or Microsoft Entra ID and an `ipFilter` policy. |
| Deleting the resource group or the virtual network fails because the subnet is in use | The service is still releasing the gateway's integration subnet | Wait a few minutes after the gateway is gone, then delete again. |

## Lab 19: Tool threat protection

Lab 19: [Protect tool calls with Agent 365 threat protection](19-tool-threat-protection/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| Every protected call returns `ToolEvaluationIdentityRequired` | The call has no bearer token, or the token isn't a delegated user token. App-only tokens and runtime keys can't be used for OBO. | Sign in with `az login` as a user, get a token for `https://azure-api.net/aigateway`, and send it as `Authorization: Bearer`. Check that the token has an `scp` claim. |
| `tools/call` returns HTTP `401` or `403` with a bearer token | The user has no data-plane role on the MCP server, or the assignment hasn't applied yet | Assign **AI Gateway Tools User** at the MCP server or gateway scope and wait a few minutes |
| Calls return `ToolEvaluationUnavailable` | The token exchange or the evaluation failed, timed out, returned an invalid verdict, or the evaluator was unavailable | Retry later. If it persists, confirm the Microsoft Defender or Microsoft Purview license and the Defender policy mode with your security team, and share the `correlationId`. |
| A benign call returns `ToolEvaluationDenied` | Defender or Purview flagged the request or the result | Review the call with your security team using the `correlationId`. If the tool already ran (after-invocation stage), don't retry it automatically. |
| You can't add a second tool threat protection policy to the server | Each MCP server can have only one tool threat protection policy | Keep the existing policy, or delete it and add a new one with the stages you want |
| Tool calls got noticeably slower | Each enabled stage adds an evaluation round trip | Keep both stages where you need them, and use only **Before tool invocation** where results are trusted |
| A script stops with HTTP `503` and `{"error":"App port is not ready"}` | The gateway is still starting after `azd up` or `azd provision` | Wait 30 seconds and run the script again. |
| A policy you added in the portal vanished after `azd provision` | A Bicep deployment sends a `PUT`, which replaces the whole MCP server | Change the azd environment values and run `azd provision` instead of editing the server in the portal. |

## Lab 20: Agent 365 governance

Lab 20: [Govern MCP servers with Agent 365](20-agent-365-governance/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| The gateway's MCP servers don't appear under **Agents** › **Tools** | Consent isn't granted, or the instance is on an API Management v1 tier | Have a tenant administrator turn on **Azure API Management service and AI Gateway** under **Agents** › **Settings** › **Gateways**. Use a v2 tier or the AI Gateway tier. |
| The server's **Tools** tab can't list its tools | The server doesn't have a static list of allowed tools, for example it uses **Allow all tools** | In the AI Gateway portal, choose **Select exact tools** on the server's **Tools** step. Otherwise, block tools in the AI Gateway portal. |
| You can't block individual tools | The instance is on an API Management v2 tier | Tool-level blocking needs the AI Gateway tier. Block the whole server instead. |
| A blocked tool still runs for some agents | Those agents call the MCP server directly, not through the gateway | Point every agent at the gateway's MCP endpoint and restrict direct access to the backend |
| An agent keeps retrying a blocked tool | The agent ignores `isError` | Check `result.isError` and the `ToolNotAvailable` denial code, and stop retrying that tool |
| Calls still fail after you unblock | Another control blocks them, such as the gateway's **Blocked tools**, **MCP server access**, or a policy | Check the server's **Basic info** and **Tools** steps and its policies in the AI Gateway portal |

## Lab 21: Enterprise reference

Lab 21: [Deploy an enterprise reference architecture](21-enterprise-reference/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| The deployment fails with `InsufficientQuota`, or the model or version isn't available | The region has no `GlobalStandard` quota for `gpt-6-luna`, or doesn't offer that version | Lower `modelCapacity`, request quota, or change `modelName`, `modelVersion`, or `--location` in your parameter file and command. |
| The gateway's `provisioningState` ends in `Failed` | Azure hit an activation or managed identity conflict, often after a gateway with the same name was deleted moments before | Delete the failed gateway and its connector gateway, wait about three minutes for the identity to be cleaned up, and deploy again. |
| The smoke test prints `Waiting for the model route` until it fails with `401`, `403`, or `404` | The new Foundry User role assignment or the model route hasn't propagated yet | Wait a few minutes and run the smoke test again. If it still fails, run the backend identity checks in [Verify](21-enterprise-reference/README.md#verify). |
| **Settings** in **Monitoring** shows "This legacy exporter no longer activates OTLP signals" | You deployed with `enableLegacyAppInsightsExporter` set to `true` | Select **Settings** › **General** › **Disable monitoring**, then **Configure telemetry** again with the same Application Insights resource. |
| `apply-baselines` fails with a validation error from the `PATCH` | A field in `baselines.json` doesn't match the current API contract, for example `counterKey` as a string instead of an array such as `["identity"]` | Create the policy once in the portal at **Gateway** scope, read the workspace with `az rest`, and copy that shape into `baselines.json`. |
| `azure/login` fails with `AADSTS70021: No matching federated identity record found` | The token subject doesn't match a federated credential | Check that the subject is exactly `repo:<github-org>/<github-repo>:environment:<name>` and that the GitHub environment name matches the job's `environment:`. |

## Lab 22: Priority and weighted routing

Lab 22: [Route an alias across models by priority and weight](22-model-routing/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| "Select models with at least one common API format." | The selected backend models don't share an interface, for example an Anthropic Messages model and an OpenAI Chat Completions model | Put models that share an interface in the same alias. |
| "Weight must be a whole number from 1 to 100.", `Each target's weight must be a whole number from 1 to 100.`, or `weight must be between 1 and 100.` | A weight is `0`, negative, or above `100` | To stop traffic to a model, raise its priority number or remove it. |
| "Priority must be a whole number from 0 to 100.", `Each target's priority must be a whole number from 0 to 100.`, or `priority must be between 0 and 100.` | A priority is outside `0` to `100` | Use `0` for the preferred tier and higher numbers for the others. |
| "Each backend model can appear only once." or `backendModels must not contain duplicate model identities.` | The same backend model is listed twice | Combine the entries and adjust the weight. |
| `This model alias already exists; use model-alias update.` | You ran `az aigateway model-alias create` for an alias that exists | Run `az aigateway model-alias update` with the same arguments. |
| All requests go to one model | The models have different priorities, so only the lowest number receives traffic | Give the models the same priority to split by weight. |
| `404` with `DeploymentNotFound` | The candidate backend model points to a Foundry deployment that doesn't exist | Create the deployment, or fix `deployment.resourceId` on the backend model. |
| `429` from the preferred model | The preferred deployment is out of capacity, and the gateway returns the error | Retry in the client, add capacity, or spread traffic with weights at the same priority. |

## Lab 23: Streaming responses

Lab 23: [Stream responses and count every token](23-streaming-responses/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `IndexError: list index out of range` in Python, or `Cannot read properties of undefined` in TypeScript | The code reads `choices[0]` on the prompt filter chunk or the usage chunk, which have no choices | Skip chunks whose `choices` array is empty, as the samples do. |
| The whole reply appears at once | curl runs without `-N`, PowerShell uses `Invoke-RestMethod`, or a proxy buffers the response | Use `curl -N`, read the stream with `HttpClient` as `stream-chat.ps1` does, and turn off response buffering in your proxy. |
| No usage chunk at the end of the stream | The client didn't set `stream_options.include_usage` | Set it when your app needs the numbers. The gateway counts the tokens for its limits either way. |
| `400` with `The 'stream_options' parameter is only allowed when 'stream' is enabled.` | The request sets `stream_options` without `"stream": true` | Send both, or neither. |
| `429` JSON response instead of a stream | A token limit on the alias, the model, or the gateway is exhausted | Wait for `Retry-After` seconds. The limit is checked before the stream starts, so no partial reply is lost. |
| The SDK sample never shows a `429` | The OpenAI SDKs retry `429` responses automatically and honor `Retry-After` | That's the behavior you want in an app. To see each `429`, create the client with `max_retries=0` (Python) or `maxRetries: 0` (TypeScript). |
| Every request in the burst returns `200` | The policy isn't active yet, or the burst used another alias | Check that `STREAM_ALIAS` matches the alias with the limit, wait a minute, and run the burst again. |

## Lab 24: GitHub Copilot BYOK

Lab 24: [Use your gateway's models and tools in GitHub Copilot](24-github-copilot-byok/README.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `HTTP 401` or "Authentication failed with provider" | The key is wrong, suspended, or deleted, or the new key isn't active yet | Check the key's state in **Access** › **Keys**, wait a minute after you create it, and paste it again. |
| `400` on every request from a custom client | The request sends both `Authorization` and `api-key` | Send one of them. Copilot sends `Authorization: Bearer` only. |
| `404`, or a "model not found" error | The model name isn't an alias on the gateway, for example the portal import's `<foundry-account-name>/gpt-6-astra` | Publish the `gpt-6-astra` alias, or set the model ID to the alias that exists. |
| The model doesn't appear in VS Code or the app | The gateway has no `/models` list to discover, or VS Code hasn't reloaded the file | Add `gpt-6-astra` by hand, then run **Developer: Reload Window** in VS Code. |
| The model is missing from the picker in Agent mode | `toolCalling` is missing or `false` | Set `"toolCalling": true` on the model. |
| VS Code or the app doesn't offer your own models at all | Your Copilot Business or Enterprise organization hasn't allowed custom models | Ask an administrator to enable them. |
| Replies are empty or cut off, or tool calls fail | The surface uses Chat Completions with a reasoning model | Set the API to Responses: `apiType` in VS Code, `COPILOT_PROVIDER_WIRE_API=responses` for the CLI, `wireApi` in the SDK. |
| `429 Too Many Requests` | Copilot used the key's 100,000 tokens for this minute | Wait for the `Retry-After` interval, or raise the token limit. |
| The CLI's first interactive prompt doesn't respond | A slow first connection | Press <kbd>Ctrl</kbd>+<kbd>C</kbd> and send the prompt again. |
| Two **GPT-6 Astra** entries in VS Code's model picker | Copilot's built-in model and yours share a name | Give yours a distinct `name`, such as `GPT-6 Astra (AI Gateway)`. |
| The MCP server doesn't start, or returns `401` | The key is sent as a bearer token, or `${AI_GATEWAY_API_KEY}` is empty where the CLI or the app runs | Send the key in the `api-key` header. Export `AI_GATEWAY_API_KEY` in the terminal, or make it available to the app and reopen it. |
| `copilot -p` doesn't use the Learn tools, or says they were denied | One-shot mode can't ask for approval | Add `--allow-tool='ai-gateway-learn'`. |
| A task with the Learn tools hits `429` or uses many tokens | Each Learn result is 25 to 50 KB | Ask for fewer lookups, publish fewer tools, or raise the token limit. |
| VS Code lists MCP servers that you didn't add | VS Code discovers servers configured in other apps | Set `chat.mcp.discovery.enabled` to `false`. |
