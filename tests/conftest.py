from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--network",
        action="store_true",
        default=False,
        help="Run tests that make real network requests",
    )
    parser.addoption(
        "--benchmark",
        action="store_true",
        default=False,
        help="Run token overhead benchmarks (writes results to tests/benchmarks/results/)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    skip_network = pytest.mark.skip(reason="pass --network to run network tests")
    skip_benchmark = pytest.mark.skip(reason="pass --benchmark to run benchmarks")
    for item in items:
        if "network" in item.keywords and not config.getoption("--network"):
            item.add_marker(skip_network)
        if "benchmark" in item.keywords and not config.getoption("--benchmark"):
            item.add_marker(skip_benchmark)
