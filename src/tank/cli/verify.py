"""tank verify command."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from tank.errors import TankError
from tank.policy.engine import Policy
from tank.validator.verify import verify

console = Console()


@click.command()
@click.argument("ctx_path", type=click.Path(path_type=Path))
@click.option(
    "--policy", type=click.Path(path_type=Path), default=None, help="Policy file path"
)
def verify_cmd(ctx_path: Path, policy: Path | None) -> None:
    """Verify the integrity of a .ctx documentation pack."""
    if not ctx_path.exists():
        console.print(f"[red]error: file not found: {ctx_path}[/red]")
        sys.exit(1)

    policy_obj = Policy.load(policy_path=policy)

    try:
        result = verify(ctx_path=ctx_path, policy=policy_obj)
    except TankError as exc:
        console.print(f"[red]error: {exc}[/red]")
        sys.exit(1)

    if result.passed:
        console.print("[green]Verification passed: pack is valid[/green]")
    else:
        step_label = f"step {result.step}" if result.step is not None else "unknown"
        console.print(
            f"[red]Verification failed at {step_label}: {result.reason}[/red]"
        )
        sys.exit(1)
