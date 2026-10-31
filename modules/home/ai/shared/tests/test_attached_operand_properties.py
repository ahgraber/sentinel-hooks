"""Operand attachment cannot remove a named target from the tamper decision."""

import shlex

from hypothesis import HealthCheck, given, settings, strategies as st
from shell_strategies import attached_operand_commands


@given(data=st.data(), name=st.text(alphabet="abcXYZ09_-= .", min_size=1, max_size=35))
@settings(
    max_examples=250,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_attached_mutations_keep_the_guarded_target(world, data, name):
    home, repo, hook = world
    target = str(home / "base" / ("file-" + name))
    command = data.draw(attached_operand_commands(target))
    assert hook.command_protected_class(command, str(repo)) == "guarded"


@given(name=st.text(alphabet="abcXYZ09_-= .", min_size=1, max_size=35))
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_equals_inside_an_ordinary_filename_is_not_a_named_operand(world, name):
    home, repo, hook = world
    target = str(home / "base" / ("file=" + name))
    assert hook.command_protected_class("rm " + shlex.quote(target), str(repo)) == "guarded"
