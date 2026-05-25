class TankError(Exception):
    """Base class for all Tank errors."""


class ManifestError(TankError):
    """Invalid or missing manifest fields."""


class SchemaValidationError(ManifestError):
    """Manifest fields fail JSON Schema validation."""


class PolicyError(TankError):
    """Pack rejected by policy."""


class VerificationError(TankError):
    """Reserved for future use: hash mismatch or archive safety failure raised as an exception.

    The current verifier returns VerifyResult dataclass objects rather than raising.
    This class is part of the public error hierarchy for callers who may wrap verify()
    in exception-based control flow in a future release.
    """


class ImportError_(TankError):
    """Database import failures."""


class BuildError(TankError):
    """Failures during pack building."""


class SearchError(TankError):
    """Database or query error during search."""


class LockfileError(TankError):
    """Malformed, missing, or incompatible tank.lock."""


class FetchError(TankError):
    """Cannot fetch a pack from a remote source_url.

    Raised when source_url is an HTTPS URL but the fetcher module is not yet
    available, or when a network error occurs during fetch.
    """


class PackNotFoundError(TankError):
    """The requested pack is not present in the local index."""
