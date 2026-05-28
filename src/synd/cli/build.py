"""tank build command."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from synd.builder.build import build_pack, build_pack_from_url
from synd.builder.url_filter import DEFAULT_NOISE_URL_PATTERNS
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
@click.option(
    "--source",
    required=True,
    type=str,
    help="Local directory or URL (llms-full.txt / llms.txt)",
)
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
@click.option(
    "--exclude-url-pattern",
    multiple=True,
    metavar="PATTERN",
    help=(
        "Additional URL path segment to exclude (e.g. 'changelog'). "
        "Can be repeated. Appended to the built-in noise list. "
        "URL builds only."
    ),
)
@click.option(
    "--no-url-filter",
    is_flag=True,
    default=False,
    help="Disable all URL noise filtering. URL builds only.",
)
def build(
    package_spec: str,
    source: str,
    output: Path,
    lifecycle: str,
    doc_version_status: str,
    owner: str | None,
    policy_profile: str | None,
    exclude_url_pattern: tuple[str, ...],
    no_url_filter: bool,
) -> None:
    """Build a documentation pack from source files or a URL.

    PACKAGE_SPEC is in the format package@version (e.g. my-lib@1.0.0).

    --source accepts a local directory or a URL ending in llms-full.txt
    or llms.txt (e.g. https://docs.example.com/llms-full.txt).

    URL builds filter out noise pages (changelogs, release notes, etc.) by
    default. Use --exclude-url-pattern to add extra patterns or --no-url-filter
    to disable filtering entirely.
    """
    try:
        pkg, ver = _parse_package_spec(package_spec)
    except SyndError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(1)

    output_dir = Path(output)

    if no_url_filter:
        url_patterns: tuple[str, ...] = ()
    else:
        url_patterns = DEFAULT_NOISE_URL_PATTERNS + tuple(exclude_url_pattern)

    try:
        if source.startswith(("http://", "https://")):
            output_dir.mkdir(parents=True, exist_ok=True)
            ctx_path = build_pack_from_url(
                package=pkg,
                version=ver,
                source_url=source,
                output=output_dir,
                lifecycle=lifecycle,
                doc_version_status=doc_version_status,
                owner=owner,
                policy_profile=policy_profile,
                excluded_url_patterns=url_patterns,
            )
        else:
            source_path = Path(source)
            if not source_path.is_dir():
                console.print(
                    f"[red]error: source directory does not exist: {source_path}[/red]"
                )
                sys.exit(1)
            output_dir.mkdir(parents=True, exist_ok=True)
            ctx_path = build_pack(
                package=pkg,
                version=ver,
                source=source_path,
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
