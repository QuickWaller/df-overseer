"""Maps a bearer token to a role. This is the credential half of the trust
boundary docs/AGENT-ARCHITECTURE.md §13 describes: **role identity must be a
credential, not a claim.** A self-declared role header would let the
Architect assert it is the Overseer and obtain write tools, silently voiding
the single-writer design (§7). So: one token per role, issued out of band and
mapped to a role server-side, never trusted from the caller.

Nothing here calls DFHack, opens a socket, or knows what HTTP is, matching
mcp/registry.py and mcp/roles.py's own scope. This module answers exactly one
question: **given a bearer token, which role (if any) does it authenticate
as.**

## Where tokens live

**This repo is public.** Real tokens go in the gitignored repo-root `.env`
(or another `infra/local.*` file), never in a tracked file --
`tests/test_no_leaked_addresses.py` guards addresses and hostnames, not
tokens, so this is on every session to get right by construction. A
commented, empty placeholder for each currently-enabled role lives in the
tracked `infra/local.example.env`, following that file's existing convention
of "real value in gitignored .env, empty/commented template committed".

`scripts/pve.py`'s `load_env` is this repo's existing precedent for reading
`.env`: strip comments and blank lines, split on the first `=`, and strip
matching surrounding quotes from the value (needed there because the Proxmox
password contains `$E`, which bash would otherwise expand to nothing). A
hand-rolled `.env` parser that skipped the quote-stripping step produced a
false alarm in this repo on 2026-09-12 (see `Working.md`). `scripts/` has no
`__init__.py`, so it is not import-able as a package from here in the
ordinary way; rather than reach across that boundary with a path hack, this
module reimplements the same, small parsing logic verbatim rather than
inventing a different one. If `scripts/pve.py`'s `load_env` ever changes,
re-check this module's `_read_dotenv` for the same fix.

## The env-var convention

One variable per role: `MCP_ROLE_TOKEN_<ROLE>`, role name upper-cased
(`MCP_ROLE_TOKEN_OVERSEER`, `MCP_ROLE_TOKEN_ARCHITECT`,
`MCP_ROLE_TOKEN_CONSULTANT`). No currently-enabled role name contains a
hyphen or anything else that does not survive `.upper()` cleanly; if one ever
does, this convention needs revisiting, not silently mangling.

## What `load_role_tokens` refuses, all hard errors at load time

Matching `roles.py`'s own style (a role's permission set is a security
boundary; strict validation belongs at load time, not scattered through
runtime checks):

1. Two roles sharing the same token.
2. A token whose env var names a role that is not enabled on the given
   roster -- catches both typos and a stale token left behind after a role
   is disabled.
3. An empty or whitespace-only token.
4. A token shorter than `MIN_TOKEN_LENGTH`.

## What this module deliberately does not do

- No server, no transport, no session handling, no rate limiting.
- No token *issuance* or rotation tooling -- tokens are pasted into `.env` by
  hand, the same way `PVE_TOKEN_SECRET` already is.
- **Never logs, prints, or returns a token value or any prefix of one.**
  Every error message below names an env var, a role, or a length -- never
  the token itself.
"""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Dict, Mapping, Optional

from .roles import Roster

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = REPO_ROOT / ".env"

_ENV_PREFIX = "MCP_ROLE_TOKEN_"

# Arbitrary but enforced: long enough that a pasted-in placeholder like
# "changeme" or a truncated copy-paste is refused rather than silently
# accepted. Not tied to any specific token format, since these are opaque
# bearer strings generated out of band, not this module's concern to mint.
MIN_TOKEN_LENGTH = 20


class AuthConfigError(Exception):
    """A gitignored token source failed a strict validation rule.

    Always a hard load-time failure, matching RegistryError/
    RoleValidationError's style: a misconfigured token source must refuse to
    load, not load with a quietly wrong role mapping.
    """


def _read_dotenv(path: Path) -> Dict[str, str]:
    """Reimplements scripts/pve.py's load_env verbatim (see module
    docstring for why this is a reimplementation, not an import): skip
    comments and blank lines, split on the first "=", strip matching
    surrounding quotes from the value.
    """
    env: Dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            env[key.strip()] = value
    return env


def _role_for_env_key(key: str) -> Optional[str]:
    if not key.startswith(_ENV_PREFIX):
        return None
    return key[len(_ENV_PREFIX):].lower()


def load_role_tokens(
    roster: Roster,
    path: Path = DEFAULT_ENV_PATH,
    minimum_length: int = MIN_TOKEN_LENGTH,
) -> Dict[str, str]:
    """Load every MCP_ROLE_TOKEN_* entry from `path` (a .env-shaped file),
    resolve each to a role, and return {token: role}.

    Raises AuthConfigError (never logging a token value) for: two roles
    sharing a token, a token naming a role not enabled on `roster`, an empty
    or whitespace token, or a token shorter than `minimum_length`.
    """
    env = _read_dotenv(Path(path))

    token_to_role: Dict[str, str] = {}
    for key, raw in env.items():
        role = _role_for_env_key(key)
        if role is None:
            continue

        if role not in roster.roles:
            raise AuthConfigError(
                f"{key} names role {role!r}, which is not an enabled role on this roster "
                "(a typo, or a token left behind after the role was disabled)"
            )

        token = raw.strip()
        if not token:
            raise AuthConfigError(f"{key} is set but empty or whitespace-only")
        if len(token) < minimum_length:
            raise AuthConfigError(
                f"{key}'s token is {len(token)} characters long; must be at least "
                f"{minimum_length}. (Length only is reported here -- never the token itself.)"
            )

        if token in token_to_role:
            other_role = token_to_role[token]
            raise AuthConfigError(
                f"{key} and MCP_ROLE_TOKEN_{other_role.upper()} resolve to the same token; "
                "two roles must not share one bearer token (length only reported, never the "
                "token itself)"
            )

        token_to_role[token] = role

    return token_to_role


def resolve(token: str, tokens: Mapping[str, str]) -> Optional[str]:
    """The role `token` authenticates as, or None if it matches nothing.

    Uses hmac.compare_digest against every configured token, rather than a
    dict lookup keyed on the secret, so the work done is independent of
    which token (if any) actually matches -- a dict lookup's timing can leak
    which prefix bytes matched via hashing/bucketing, and a lookup that
    short-circuits on the first match leaks which position in the mapping
    matched. Deliberately does not `break` on a match, for the same reason:
    every configured token is compared exactly once regardless of outcome.
    """
    if not token:
        return None

    token_bytes = token.encode("utf-8")
    matched_role: Optional[str] = None
    for candidate, role in tokens.items():
        if hmac.compare_digest(candidate.encode("utf-8"), token_bytes):
            matched_role = role
    return matched_role
