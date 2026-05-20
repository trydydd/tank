from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--network",
        action="store_true",
        default=False,
        help="Run tests that make real network requests",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not config.getoption("--network"):
        skip = pytest.mark.skip(reason="pass --network to run network tests")
        for item in items:
            if "network" in item.keywords:
                item.add_marker(skip)
