"""PyDeadwood: find dead code in Python projects without running them.

The public API is intentionally small:

- :func:`pydeadwood.core.analyze` scans directories and returns findings.
- :class:`pydeadwood.core.Finding` describes one finding.

Only the standard library is used, and target code is parsed with
``ast`` but never imported or executed.
"""

from .core import Finding, analyze

__version__ = "1.0.0"
__all__ = ["Finding", "analyze", "__version__"]
