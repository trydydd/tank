"""tank build command."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from synd.builder.build import build_pack, build_pack_from_url
from synd.builder.chunking import (
    RawChunk,
    _DEFAULT_MAX_CHUNK_TOKENS,
    _DEFAULT_MIN_CHUNK_TOKENS,
)
from synd.builder.url_filter import DEFAULT_NOISE_URL_PATTERNS
from synd.cli.exit_codes import EXIT_USAGE, exit_code_for
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
@click.option(
    "--max-chunk-tokens",
    default=None,
    type=int,
    help="Max tokens per chunk before overflow split. [default: 800]",
)
@click.option(
    "--min-chunk-tokens",
    default=None,
    type=int,
    help="Min tokens to emit a chunk; stubs below this are merged into the next section. [default: 20]",
)
@click.option(
    "--warn-chunk-tokens",
    default=None,
    type=int,
    help=(
        "Warn when a chunk exceeds this token count after all splits. "
        "Defaults to 2× --max-chunk-tokens."
    ),
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
    max_chunk_tokens: int | None,
    min_chunk_tokens: int | None,
    warn_chunk_tokens: int | None,
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
        # Malformed package@version is a usage error, not a build failure.
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(EXIT_USAGE)

    output_dir = Path(output)

    if no_url_filter:
        url_patterns: tuple[str, ...] = ()
    else:
        url_patterns = DEFAULT_NOISE_URL_PATTERNS + tuple(exclude_url_pattern)

    resolved_max = (
        max_chunk_tokens if max_chunk_tokens is not None else _DEFAULT_MAX_CHUNK_TOKENS
    )
    resolved_min = (
        min_chunk_tokens if min_chunk_tokens is not None else _DEFAULT_MIN_CHUNK_TOKENS
    )

    try:
        if source.startswith(("http://", "https://")):
            output_dir.mkdir(parents=True, exist_ok=True)
            ctx_path, oversized = build_pack_from_url(
                package=pkg,
                version=ver,
                source_url=source,
                output=output_dir,
                lifecycle=lifecycle,
                doc_version_status=doc_version_status,
                owner=owner,
                policy_profile=policy_profile,
                excluded_url_patterns=url_patterns,
                max_chunk_tokens=resolved_max,
                min_chunk_tokens=resolved_min,
                warn_chunk_tokens=warn_chunk_tokens,
            )
        else:
            source_path = Path(source)
            if not source_path.is_dir():
                console.print(
                    f"[red]error: source directory does not exist: {source_path}[/red]"
                )
                sys.exit(EXIT_USAGE)
            output_dir.mkdir(parents=True, exist_ok=True)
            ctx_path, oversized = build_pack(
                package=pkg,
                version=ver,
                source=source_path,
                output=output_dir,
                lifecycle=lifecycle,
                doc_version_status=doc_version_status,
                owner=owner,
                policy_profile=policy_profile,
                max_chunk_tokens=resolved_max,
                min_chunk_tokens=resolved_min,
                warn_chunk_tokens=warn_chunk_tokens,
            )
        console.print(f"[green]Pack built: {ctx_path}[/green]")
        _print_oversized_warnings(oversized, resolved_max, warn_chunk_tokens)
    except SyndError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(exit_code_for(exc))


def _print_oversized_warnings(
    oversized: list[RawChunk],
    max_chunk_tokens: int,
    warn_chunk_tokens: int | None,
) -> None:
    if not oversized:
        return
    effective_warn = (
        warn_chunk_tokens if warn_chunk_tokens is not None else 2 * max_chunk_tokens
    )
    _MAX_LISTED = 5
    console.print(
        f"[yellow]  {len(oversized)} chunk(s) exceed {effective_warn:,} tokens "
        f"— run `synd inspect` on the pack for details.[/yellow]"
    )
    for rc in oversized[:_MAX_LISTED]:
        console.print(f"[yellow]    • {rc.heading_path} ({rc.token_count:,}t)[/yellow]")
    if len(oversized) > _MAX_LISTED:
        console.print(f"[yellow]    … and {len(oversized) - _MAX_LISTED} more[/yellow]")
