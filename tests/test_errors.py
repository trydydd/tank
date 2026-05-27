from synd.errors import (
    BuildError,
    ImportError_,
    ManifestError,
    PolicyError,
    SearchError,
    SyndError,
    VerificationError,
)


def test_tank_error_is_exception() -> None:
    assert issubclass(SyndError, Exception)


def test_subclasses_inherit_tank_error() -> None:
    for cls in (
        ManifestError,
        PolicyError,
        VerificationError,
        ImportError_,
        BuildError,
        SearchError,
    ):
        assert issubclass(cls, SyndError)


def test_error_message_preserved() -> None:
    msg = "something went wrong"
    err = SyndError(msg)
    assert str(err) == msg

    err2 = ManifestError("manifest is missing version")
    assert str(err2) == "manifest is missing version"
