"""Zero Ops SRE Agent Recipe tooling.

Offline, credential-free by design. Nothing in this package may import an Azure
SDK, read a credential, or make a network call: FR-25 requires configuration to
validate on a machine with no Azure access, and a dependency acquired later
would erode that guarantee silently rather than loudly.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
