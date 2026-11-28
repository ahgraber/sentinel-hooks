"""Run the Pi tests against an empty home and no harness variables, so no case reads the developer's setup."""

from pathlib import Path
import sys

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".specs").is_dir())

sys.path.append(str(REPO_ROOT / "tests" / "shared"))
from hermetic import isolate_test_environment  # noqa: E402

isolate_test_environment()
