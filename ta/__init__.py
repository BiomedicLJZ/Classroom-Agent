"""TA agent package.

Silences noisy warnings emitted by the NVIDIA LangChain integration so the CLI
output stays clean: non-default kwargs (reasoning_budget, chat_template_kwargs)
routed to model_kwargs, the max_tokens deprecation, and the "model type unknown"
notice. These are expected for the free Nemotron endpoint and not actionable.
"""
import warnings

_NVIDIA_WARNING_PATTERNS = (
    r".*reasoning_budget is not default parameter.*",
    r".*chat_template_kwargs is not default parameter.*",
    r".*max_tokens.*deprecated.*",
    r".*type is unknown and inference may fail.*",
)

for _pattern in _NVIDIA_WARNING_PATTERNS:
    warnings.filterwarnings("ignore", message=_pattern)
