"""Differentiated, stable CLI exit codes.

A documented taxonomy so CI and shell scripts can branch on the *class* of
outcome rather than just success/failure. These codes are a stable contract:
future changes are additive only (new codes), never reassigned.

| Code | Meaning                         | Typical trigger                                   |
|------|---------------------------------|---------------------------------------------------|
| 0    | success                         | normal completion                                 |
| 1    | generic/unexpected error        | uncaught SyndError with no specific mapping       |
| 2    | usage error                     | bad arguments / missing input path (Click native) |
| 3    | policy rejection                | PolicyError, or verify failed at step 3 (policy)  |
| 4    | verification/integrity failure  | VerificationError, schema/manifest, verify steps  |
| 5    | not found                       | PackNotFoundError (pack absent from the index)    |
| 6    | build/IO failure                | BuildError, FetchError, LockfileError             |

Note: a *missing or malformed CLI argument* (including a path that does not
exist) is a usage error (2) by Click convention. Code 6 is reserved for
operations that fail after well-formed inputs are accepted.
"""

from __future__ import annotations

from synd.errors import (
    BuildError,
    FetchError,
    LockfileError,
    ManifestError,
    PackNotFoundError,
    PolicyError,
    SyndError,
    VerificationError,
)

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_POLICY = 3
EXIT_VERIFICATION = 4
EXIT_NOT_FOUND = 5
EXIT_BUILD = 6

# Most-specific first. SchemaValidationError is a ManifestError subclass, so the
# ManifestError entry also covers it; both map to the verification class.
_TABLE: tuple[tuple[type[SyndError], int], ...] = (
    (PackNotFoundError, EXIT_NOT_FOUND),
    (PolicyError, EXIT_POLICY),
    (VerificationError, EXIT_VERIFICATION),
    (ManifestError, EXIT_VERIFICATION),
    (FetchError, EXIT_BUILD),
    (LockfileError, EXIT_BUILD),
    (BuildError, EXIT_BUILD),
)


def exit_code_for(exc: BaseException) -> int:
    """Map an exception to its CLI exit code.

    Known SyndError subclasses map per the taxonomy table; anything else
    (including non-SyndError exceptions) maps to the generic error code.
    """
    for exc_type, code in _TABLE:
        if isinstance(exc, exc_type):
            return code
    return EXIT_ERROR


def verify_failure_code(step: int | None) -> int:
    """Exit code for a failed VerifyResult.

    A failure at step 3 is a policy rejection (3); every other step is a
    verification/integrity failure (4).
    """
    return EXIT_POLICY if step == 3 else EXIT_VERIFICATION
