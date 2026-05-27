"""tank build command."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from synd.builder.build import build_pack
from synd.errors import BuildError, SyndError

console = Console()


def _parse_package_spec(spec: str) -> tuple[str, str]:
    """Parse 'package@version' string.

    Returns (package, version).
    Raises BuildError on invalid format.
    """
    if "@" not in spec:
        raise BuildError(
            f"Missing '@' in package spec '{spec}'. "
            "Expected format: package@version (e.g. my-lib@1.0.0)"
        )
    parts = spec.split("@")
    if len(parts) != 2:
        raise BuildError(
            f"Invalid package spec '{spec}'. "
            "Multiple '@' signs detected. Expected format: package@version"
        )
    pkg, ver = parts[0], parts[1]
    if not pkg or not ver:
        raise BuildError(
            f"Invalid package spec '{spec}'. "
            "Package name and version must be non-empty."
        )
    return pkg, ver


@click.command()
@click.argument("package_spec")
@click.option("--source", required=True, type=click.Path(path_type=Path))
@click.option("--output", type=click.Path(path_type=Path), default=Path("."))
@click.option(
    "--lifecycle", default="draft", help="Lifecycle state (draft, approved, deprecated)"
)
@click.option(
    "--doc-version-status",
    default="stable",
    help="Documentation version status (stable, prerelease, archived, unknown)",
)
@click.option("--owner", default=None, help="Owner/team name")
@click.option("--policy-profile", default=None, help="Policy profile name")
def build(
    package_spec: str,
    source: Path,
    output: Path,
    lifecycle: str,
    doc_version_status: str,
    owner: str | None,
    policy_profile: str | None,
) -> None:
    """Build a documentation pack from source files.

    PACKAGE_SPEC is in the format package@version (e.g. my-lib@1.0.0).
    """
    try:
        pkg, ver = _parse_package_spec(package_spec)
    except SyndError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(1)

    if not source.is_dir():
        console.print(f"[red]error: source directory does not exist: {source}[/red]")
        sys.exit(1)

    try:
        output_dir = Path(output)
        output_dir.mkdir(parents=True, exist_ok=True)
        ctx_path = build_pack(
            package=pkg,
            version=ver,
            source=source,
            output=output_dir,
            lifecycle=lifecycle,
            doc_version_status=doc_version_status,
            owner=owner,
            policy_profile=policy_profile,
        )
        console.print(f"[green]Pack built: {ctx_path}[/green]")
    except SyndError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(1)
