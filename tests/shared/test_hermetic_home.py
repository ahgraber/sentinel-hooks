"""The suite runs against a home of its own and no harness variables, never the developer's setup."""

import os
from pathlib import Path
import pwd

from hermetic import HARNESS_VARIABLES


def test_the_suite_runs_against_a_home_of_its_own() -> None:
    home = Path(os.environ["HOME"])
    assert home != Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert home.name.startswith("sentinel-test-home-")


def test_the_suite_runs_without_harness_variables() -> None:
    assert [name for name in HARNESS_VARIABLES if name in os.environ] == []
