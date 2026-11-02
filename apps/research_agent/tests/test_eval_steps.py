"""Live single-step evals of the research agent: `pytest --agentkit-live -k eval_steps`."""

import pytest
from agentkit_evals.pytest_plugin import assert_case


@pytest.mark.agentkit_eval(
    dataset="../evals/steps.jsonl", agent="../agent.yaml", kind="single_step"
)
def test_first_step(case, agentkit_run):
    assert_case(agentkit_run(case), step_pass=1.0)
