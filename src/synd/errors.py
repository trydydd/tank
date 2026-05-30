class SyndError(Exception):
    """Base class for all Synaptic Drift errors."""


class ManifestError(SyndError):
    """Invalid or missing manifest fields."""


class SchemaValidationError(ManifestError):
    """Manifest fields fail JSON Schema validation."""


class PolicyError(SyndError):
    """Pack rejected by policy."""


class VerificationError(SyndError):
    """Reserved for future use: hash mismatch or archive safety failure raised as an exception.

    The current verifier returns VerifyResult dataclass objects rather than raising.
    This class is part of the public error hierarchy for callers who may wrap verify()
    in exception-based control flow in a future release.
    """


class ImportError_(SyndError):
    """Database import failures."""


class BuildError(SyndError):
    """Failures during pack building."""


class SearchError(SyndError):
    """Database or query error during search."""


class LockfileError(SyndError):
    """Malformed, missing, or incompatible synd.lock."""


class FetchError(SyndError):
    """Cannot fetch a pack from a remote source_url.

    Raised when source_url is an HTTPS URL but the fetcher module is not yet
    available, or when a network error occurs during fetch.
    """


class PackNotFoundError(SyndError):
    """The requested pack is not present in the local index."""
