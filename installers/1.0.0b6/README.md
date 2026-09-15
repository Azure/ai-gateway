# AI Gateway CLI 1.0.0b6 candidate

**Locally enabled; not published or live.** These standalone installers embed
the proposed wheel URL below and require its pinned SHA-256 before installing.
Publication and alias activation have not been performed. Do not run the
proposed commands against the current aliases.

## Exact payload

Proposed release: `cli-v1.0.0b6`.

Proposed wheel URL (not verified live):

```text
https://github.com/Azure/ai-gateway/releases/download/cli-v1.0.0b6/aigateway-1.0.0b6-py3-none-any.whl
```

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `aigateway-1.0.0b6-py3-none-any.whl` | 167181 | `77a604d0f301f330602f430f22130b99af904dc627f44d3d035bf61c6354fe76` |
| `install.sh` | 6925 | `b1bbaac5253198aa46b6de9c0995ac525a8f92ba8abb7b8220127bad6b6ad90e` |
| `install.ps1` | 9896 | `bdd84a09eb27a1b60d614978325d0ea3b0e27a356148db686a86aa32e1766f2f` |

The wheel is an exact original build artifact, not a local rebuild. Hash
verification establishes byte integrity, not signature or policy verification.
The installer also checks extension name/version and API version
`2025-09-01-preview`. It has no private authentication or latest-build fallback.

## Prerequisites and boundaries

POSIX requires `sh`, Azure CLI (`az` on PATH), `curl`, standard utilities
`mktemp`, `mkdir`, `rm`, `env`, `grep`, `cat`, `tr`, and either `sha256sum` or
`shasum`. PowerShell uses native HTTP and standard Core/Utility/Management
cmdlets plus .NET HTTP/IO; it requires `az` but **does not require curl**.
Both need writable temporary/CLI locations and trusted HTTPS connectivity.
The bootstrap uses existing proxy/TLS settings; no certificate checks are disabled.

Base installation needs neither GitHub CLI nor a separate Python/pip install.
Optional `az aigateway mcp create --github` requires `gh` even with `GH_TOKEN`;
generic `--endpoints` does not invoke that branch.

Local acceptance used macOS `/bin/sh`, PowerShell 7.6.3 and isolated Azure CLI
2.87.0/Python 3.13.15 with the exact wheel. **Script retrieval and wheel HTTP
were mocked.** Native Windows PowerShell 5.1/Windows `az.cmd`, older CLI versions,
clean-machine dependency closure and actual proxy/network delivery remain
unverified. Installation uses the user's CLI extension/config locations unless
the caller explicitly isolates them; it can replace an existing extension.

## Proposed invocation after authorized activation

POSIX: retrieve the script, verify its hash, and only then execute it:

```sh
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
  https://aka.ms/aigateway-cli-install --output install-aigateway.sh &&
(
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\n' b1bbaac5253198aa46b6de9c0995ac525a8f92ba8abb7b8220127bad6b6ad90e install-aigateway.sh | sha256sum --check
  else
    printf '%s  %s\n' b1bbaac5253198aa46b6de9c0995ac525a8f92ba8abb7b8220127bad6b6ad90e install-aigateway.sh | shasum -a 256 --check
  fi
) &&
sh ./install-aigateway.sh
```

Uninstall using the previously verified local script:

```sh
sh ./install-aigateway.sh --uninstall
```

PowerShell installation and uninstall:

```powershell
irm https://aka.ms/aigateway-cli-install-ps | iex
& ([scriptblock]::Create((irm https://aka.ms/aigateway-cli-install-ps))) -Uninstall
```

The convenience `irm | iex` bootstrap trusts the alias and HTTPS script host;
the embedded digest verifies the wheel, not the bootstrap script. For a
script-verification-first workflow, download the script with
`Invoke-WebRequest -OutFile`, compare `Get-FileHash -Algorithm SHA256` with the
table, and execute only if equal. Do not bypass local execution policy.

Proposed alias targets (the final public commit is not yet known):

```text
https://raw.githubusercontent.com/Azure/ai-gateway/<APPROVED_PUBLIC_COMMIT>/installers/1.0.0b6/install.sh
https://raw.githubusercontent.com/Azure/ai-gateway/<APPROVED_PUBLIC_COMMIT>/installers/1.0.0b6/install.ps1
```

These are script URLs, distinct from the wheel URL. Use a full reviewed commit,
not a moving branch, GitHub blob page, login page or expiring download link.
Verify anonymous HTTPS/raw bytes and script hashes before repointing aliases,
then test both actual aliases end to end in disposable CLI environments without
mocks. Record current targets before changing them. Roll back only to a previous
approved working pinned target; if none exists, suspend installation instructions
and select a fail-closed maintenance target rather than restoring a broken link.

The standalone scripts include their MIT copyright and permission notice.
