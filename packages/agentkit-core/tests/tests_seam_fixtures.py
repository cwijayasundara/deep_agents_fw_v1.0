"""Provider factories referenced by fake entry points in test_seams.py."""

from agentkit_core.seams import provider


@provider(owner="platform", version="1.0.0")
def alpha(settings):
    return "alpha"


@provider(owner="tenant-b", version="1.0.0", tenants=["tenant-b"])
def beta_b_only(settings):
    return "beta"


@provider(owner="platform", version="1.0.0")
def alpha_again(settings):
    return "alpha-again"
