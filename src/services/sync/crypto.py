"""Passphrase encryption for profile archives (scrypt + chunked AES-256-GCM).

A profile archive holds live logins, so it is encrypted before it leaves the
machine. Format: MAGIC | salt(16) | chunks, each `len(4) | nonce-less GCM blob`;
the nonce is the chunk counter, and the last-chunk flag is bound as AAD so a
truncated file fails to decrypt.
"""

from __future__ import annotations

import os
import struct
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"FPX1"
CHUNK = 4 * 1024 * 1024
_SALT = 16


class DecryptError(Exception):
    pass


def _key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def _nonce(counter: int) -> bytes:
    return struct.pack(">4xQ", counter)


def encrypt_stream(src: BinaryIO, dst: BinaryIO, passphrase: str) -> None:
    if not passphrase:
        raise ValueError("A passphrase is required")
    salt = os.urandom(_SALT)
    aes = AESGCM(_key(passphrase, salt))
    dst.write(MAGIC + salt)
    counter = 0
    block = src.read(CHUNK)
    while True:
        nxt = src.read(CHUNK)
        last = not nxt
        blob = aes.encrypt(_nonce(counter), block, b"\x01" if last else b"\x00")
        dst.write(struct.pack(">I", len(blob)) + blob)
        if last:
            return
        block, counter = nxt, counter + 1


def decrypt_stream(src: BinaryIO, dst: BinaryIO, passphrase: str) -> None:
    head = src.read(len(MAGIC) + _SALT)
    if len(head) != len(MAGIC) + _SALT or not head.startswith(MAGIC):
        raise DecryptError("Not a FoxProfile encrypted archive")
    aes = AESGCM(_key(passphrase, head[len(MAGIC) :]))
    counter = 0
    seen_last = False
    while True:
        raw = src.read(4)
        if not raw:
            break
        if seen_last or len(raw) != 4:
            raise DecryptError("Corrupt archive")
        (size,) = struct.unpack(">I", raw)
        blob = src.read(size)
        if len(blob) != size:
            raise DecryptError("Truncated archive")
        peek = src.read(1)
        last = not peek
        if peek:
            src.seek(-1, os.SEEK_CUR)
        try:
            dst.write(aes.decrypt(_nonce(counter), blob, b"\x01" if last else b"\x00"))
        except InvalidTag as e:
            raise DecryptError("Wrong passphrase or corrupted archive") from e
        seen_last = last
        counter += 1
    if not seen_last:
        raise DecryptError("Truncated archive")
