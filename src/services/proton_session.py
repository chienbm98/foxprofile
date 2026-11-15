"""Prepare a Chrome profile's Proton VPN session before the browser opens.

The extension has no login form for scripts; it reads the session from its own
storage (`bex-session`) and connects through the popup. This CLI drives a
headless Chrome with the profile's extension:

    python -m src.services.proton_session prepare muse1 --country US

`prepare` logs in against the profile's Proton account and connects to the
chosen country; the normal launch then only has to open the browser.
`harvest` logs in through a temporary Chrome profile and writes the session
tokens to a 0600 file; `inject` writes such a session into a target profile.
A session is one Proton session: its refresh token rotates, so do not inject
the same harvested session into several profiles that will refresh it.

Chrome only: the normal Camoufox launch already drives the extension through
Marionette, so these commands are only needed for Chrome sessions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

from ..core.config import profile_data_dir
from ..models.profile import Profile, country_or_none
from ..utils.files import write_private
from . import proton_account
from .browser import extensions, proton_login
from .browser.proton_countries import BY_CODE
from .profile.manager import ProfileManager


def _profile_dir(profile: Profile) -> str:
    return profile_data_dir(profile.name)


def _write_session(path: Path, session: dict) -> None:
    write_private(path, json.dumps(session, indent=2).encode("utf-8"))


def _read_session(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("uid") or not data.get("refreshToken"):
        raise ValueError("session file must contain uid and refreshToken")
    return data


def _require(profile: Profile | None, name: str) -> Profile:
    if profile is None:
        raise SystemExit(f"profile not found: {name}")
    if profile.engine != "chrome":
        raise SystemExit(
            "this command only prepares Chrome profiles; Camoufox uses the "
            "Sign in button in the extension"
        )
    if profile.proxy_mode != "proton":
        raise SystemExit(f"{name} is not in Proton VPN mode")
    return profile


def _account(name: str) -> proton_account.ProtonAccount:
    account = proton_account.load(name)
    if not account.configured:
        raise SystemExit(f"no Proton account saved for {name}; enter one in the profile dialog")
    return account


def _country(value: str | None, profile: Profile) -> str:
    country = country_or_none(value if value is not None else profile.proton_country)
    if country and country not in BY_CODE:
        raise SystemExit(f"unknown Proton country code: {country}")
    return country


def _engine(profile: Profile, profile_dir: str, *, headless: bool, proxy: str | None = None):
    from chrome_engine.engine import ChromeEngine

    extra_args = extensions.chromium_extra_args(("proton-vpn",))
    if not extra_args:
        raise SystemExit("could not prepare the Proton VPN extension")
    return ChromeEngine(
        profile_dir,
        platform=profile.os_type,
        proxy=proxy if proxy is not None else profile.proxy,
        headless=headless,
        extra_args=extra_args,
    )


async def prepare(
    name: str,
    *,
    country: str | None = None,
    visible: bool = False,
    log=print,
) -> bool:
    """Log in and connect in the target profile, before the normal launch."""
    profile = _require(ProfileManager().profiles.get(name), name)
    account = _account(name)
    code = _country(country, profile)
    profile_dir = _profile_dir(profile)
    engine = _engine(profile, profile_dir, headless=not visible)
    try:
        context = await engine.start()
        try:
            return await proton_login._chromium_login(
                context,
                profile_dir,
                account,
                keep_open=visible,
                log=log,
                country=code,
            )
        finally:
            await engine.stop()
    except Exception as e:
        log(f"prepare failed: {type(e).__name__}: {' '.join(str(e).split())[:200]}")
        return False


async def harvest(name: str, out: Path, *, log=print) -> bool:
    """Log in through a temporary Chrome profile and write the session file."""
    profile = _require(ProfileManager().profiles.get(name), name)
    account = _account(name)
    directory = tempfile.mkdtemp(prefix="foxprofile-proton-")
    try:
        engine = _engine(profile, directory, headless=True, proxy=profile.proxy)
        try:
            context = await engine.start()
            try:
                if not await proton_login._chromium_login(
                    context, directory, account, keep_open=False, log=log
                ):
                    return False
                probe, session = await proton_login._chromium_session(context)
                await probe.close()
                if not session.get("uid") or not session.get("refreshToken"):
                    log("harvest: the extension did not store a session")
                    return False
                _write_session(out, session)
                log(f"harvest: wrote the session to {out}")
                return True
            finally:
                await engine.stop()
        except Exception as e:
            log(f"harvest failed: {type(e).__name__}: {' '.join(str(e).split())[:200]}")
            return False
    finally:
        shutil.rmtree(directory, ignore_errors=True)


async def inject(
    name: str,
    session_path: Path,
    *,
    country: str | None = None,
    visible: bool = False,
    log=print,
) -> bool:
    """Write a harvested session into the target profile and connect."""
    profile = _require(ProfileManager().profiles.get(name), name)
    code = _country(country, profile)
    try:
        session = _read_session(session_path)
    except (OSError, ValueError) as e:
        raise SystemExit(f"cannot read session: {e}") from e
    session.setdefault("persistent", True)
    profile_dir = _profile_dir(profile)
    engine = _engine(profile, profile_dir, headless=not visible)
    try:
        context = await engine.start()
        try:
            probe, _ = await proton_login._chromium_session(context)
            await probe.evaluate(
                "async (session) => { await chrome.storage.local.set({'bex-session': session}); }",
                session,
            )
            log("inject: wrote the session into the extension")
            await proton_login._connect_country(context, code, log)
            return True
        finally:
            await engine.stop()
    except Exception as e:
        log(f"inject failed: {type(e).__name__}: {' '.join(str(e).split())[:200]}")
        return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.services.proton_session",
        description="Prepare a Chrome profile's Proton VPN session before launch",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare", help="log in and connect in the target profile")
    p_prepare.add_argument("profile")
    p_prepare.add_argument(
        "--country", default=None, help="ISO code, e.g. US; empty = Quick Connect"
    )
    p_prepare.add_argument("--visible", action="store_true", help="show the browser window")

    p_harvest = sub.add_parser("harvest", help="log in a temporary profile and write the session")
    p_harvest.add_argument("profile")
    p_harvest.add_argument("--out", required=True, type=Path)

    p_inject = sub.add_parser("inject", help="write a harvested session into the profile")
    p_inject.add_argument("profile")
    p_inject.add_argument("--session", required=True, type=Path)
    p_inject.add_argument("--country", default=None)
    p_inject.add_argument("--visible", action="store_true")

    args = parser.parse_args(argv)
    manager = ProfileManager()

    if args.command == "prepare":
        ok = asyncio.run(prepare(args.profile, country=args.country, visible=args.visible))
        if ok and args.country is not None:
            manager.set_proton_country(args.profile, args.country)
        return 0 if ok else 1
    if args.command == "harvest":
        return 0 if asyncio.run(harvest(args.profile, args.out)) else 1
    if args.command == "inject":
        ok = asyncio.run(
            inject(
                args.profile,
                args.session,
                country=args.country,
                visible=args.visible,
            )
        )
        if ok and args.country is not None:
            manager.set_proton_country(args.profile, args.country)
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
