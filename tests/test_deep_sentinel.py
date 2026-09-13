import pytest


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_deep_lane_sentinel():
    """A minimal deep-marked test that proves marker selection and the deep budget.

    Convention for later deep tests: pair pytest.mark.deep with
    pytest.mark.timeout(300), matching the deep lane's per-test budget. This
    sentinel carries no other purpose and needs no fixture or delivery tool.
    """
    assert True
