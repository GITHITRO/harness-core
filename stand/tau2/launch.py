"""tau2 CLI with the harness agent registered. Usage: same as `tau2`, e.g. launch.py run --agent harness_agent ..."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tau2.registry import registry  # noqa: E402

from harness_agent import create_harness_agent  # noqa: E402

registry.register_agent_factory(create_harness_agent, "harness_agent")

from tau2.cli import main  # noqa: E402

sys.exit(main())
