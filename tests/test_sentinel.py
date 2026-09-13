def test_verdict_path_sentinel(request):
    """The seen-red lane fails one real assertion and leaves all other tests live."""
    if request.config.getoption("--evorthon-inject-assertion", default=False):
        assert False, "deliberate assertion used only to prove the verdict path"
