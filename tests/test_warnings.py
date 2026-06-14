# tests/test_warnings.py
import warnings


def test_nvidia_integration_warnings_suppressed():
    """Importing ta installs ignore-filters for the noisy NVIDIA LangChain
    integration warnings (non-default kwargs, max_tokens deprecation, unknown
    model type)."""
    import ta
    # pytest resets warnings.filters per test, so re-apply explicitly before checking.
    ta._install_nvidia_warning_filters()
    keys = ("reasoning_budget", "chat_template_kwargs", "max_tokens", "type is unknown")
    ignored = [
        f for f in warnings.filters
        if f[0] == "ignore" and f[1] is not None
        and any(k in f[1].pattern for k in keys)
    ]
    assert ignored, "expected ignore filters for the NVIDIA integration warnings"
