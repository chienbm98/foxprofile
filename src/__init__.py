"""FoxProfile.

FOXPROFILE_CAMOUFOX_HOME makes Camoufox look for its browser, add-ons and GeoIP database in
that folder instead of the per-user cache, so an app folder on a USB stick can carry its own
browser and run on any PC without downloading it. Camoufox reads the location when it is
imported, so the override has to happen here, before anything imports it.
"""

import os as _os

_camoufox_home = _os.environ.get("FOXPROFILE_CAMOUFOX_HOME", "").strip()
if _camoufox_home:
    try:
        import platformdirs as _platformdirs

        _original_user_cache_dir = _platformdirs.user_cache_dir

        def _user_cache_dir(appname=None, *args, **kwargs):  # type: ignore[no-untyped-def]
            if appname == "camoufox":
                return _camoufox_home
            return _original_user_cache_dir(appname, *args, **kwargs)

        _platformdirs.user_cache_dir = _user_cache_dir
    except ImportError:
        pass
