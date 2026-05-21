class TankError(Exception):
    """Base class for all Tank errors."""


class ManifestError(TankError):
    """Invalid or missing manifest fields."""


class PolicyError(TankError):
    """Pack rejected by policy."""


class VerificationError(TankError):
    """Hash mismatch or archive safety failure."""


class ImportError_(TankError):
    """Database import failures."""


class BuildError(TankError):
    """Failures during pack building."""


class SearchError(TankError):
    """Database or query error during search."""
