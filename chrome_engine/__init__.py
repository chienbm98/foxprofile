"""Chrome engine for FoxProfile, built on fingerprint-chromium.

An experimental second browser engine next to Camoufox: a patched Chromium
whose fingerprint (navigator, client hints, WebGL, canvas, audio, fonts) is
spoofed in C++ from a per-profile seed. See chrome_engine/README.md.
"""

from .engine import ChromeEngine, EngineError, EngineNotInstalled
from .persona import Persona
from .release import DEFAULT_VERSION

__all__ = ["DEFAULT_VERSION", "ChromeEngine", "EngineError", "EngineNotInstalled", "Persona"]
