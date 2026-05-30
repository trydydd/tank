"""tank verify command."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from synd.cli.exit_codes import exit_code_for, verify_failure_code
from synd.errors import SyndError
from synd.policy.engine import Policy
from synd.validator.verify import verify

console = Console()


@click.command()
@click.argument("ctx_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--policy", type=click.Path(path_type=Path), default=None, help="Policy file path"
)
def verify_cmd(ctx_path: Path, policy: Path | None) -> None:
    """Verify the integrity of a .ctx documentation pack."""
    try:
        policy_obj = Policy.load(policy_path=policy)
        result = verify(ctx_path=ctx_path, policy=policy_obj)
    except SyndError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(exit_code_for(exc))

    if result.passed:
        console.print("[green]Verification passed: pack is valid[/green]")
    else:
        step_label = f"step {result.step}" if result.step is not None else "unknown"
        console.print(
            f"[red]Verification failed at {step_label}: {result.reason}[/red]"
        )
        sys.exit(verify_failure_code(result.step))
