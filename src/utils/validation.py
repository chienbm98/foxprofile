import re

from ..core.strings import get_string

_INVALID_CHARS = '<>:"/\\|?*'
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_PROXY_PATTERN = re.compile(
    r"^(?:(?P<scheme>https?|socks[45])://)?"
    r"(?:(?P<user>[^:@]+):(?P<pass>[^@]+)@)?"
    r"(?P<host>[a-zA-Z0-9.-]+|\d{1,3}(?:\.\d{1,3}){3})"
    r":(?P<port>\d{1,5})$",
)


def validate_profile_name(name: str) -> tuple[bool, str]:
    if not name:
        return False, get_string("validation_empty_name")

    if len(name) > 64:
        return False, get_string("validation_name_too_long")

    found_invalid = [c for c in name if c in _INVALID_CHARS]
    if found_invalid:
        return False, get_string("validation_invalid_chars", chars=", ".join(found_invalid))

    if name != name.strip():
        return False, get_string("validation_name_spaces")

    # The name becomes a directory under DATA_DIR: "." and ".." would resolve
    # to DATA_DIR or its parent (and deleting the profile would delete them),
    # and Windows silently strips trailing dots.
    if name.endswith("."):
        return False, get_string("validation_trailing_dot")

    if name.upper() in _RESERVED_NAMES:
        return False, get_string("validation_reserved_name", name=name)

    return True, ""


def validate_proxy_format(proxy_str: str) -> tuple[bool, str]:
    if not proxy_str:
        return True, ""

    match = _PROXY_PATTERN.match(proxy_str)
    if not match:
        return False, get_string("validation_invalid_proxy")

    port = int(match.group("port"))
    if not 1 <= port <= 65535:
        return False, get_string("validation_invalid_port", port=port)

    return True, ""
