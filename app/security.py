# -*- coding: utf-8 -*-
#source: https://stackoverflow.com/questions/9594125/salt-and-hash-a-password-in-python

import bcrypt
import os


# bcrypt is intentionally slow: the default 12 rounds take ~0.4s per
# operation. Tests set WLT_BCRYPT_ROUNDS to a lower value (e.g. 4) to
# keep the suite fast; the round count is embedded in the hash itself, so
# verification always works regardless of the current value.
_BCRYPT_ROUNDS = int(os.environ.get('WLT_BCRYPT_ROUNDS', '12'))


def _as_bytes(value):
    return value.encode('utf-8') if isinstance(value, str) else value


def get_hashed_password(plain_text_password):
    # Hash a password for the first time
    #   (Using bcrypt, the salt is saved into the hash itself)
    #
    # py-bcrypt (0.4) accepts str and returns str; modern bcrypt needs
    # and returns bytes. Try bytes first, then fall back to str, and
    # always store the hash as str.
    try:
        hashed = bcrypt.hashpw(_as_bytes(plain_text_password),
                               bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
    except (TypeError, UnicodeError):
        hashed = bcrypt.hashpw(plain_text_password,
                               bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))

    return hashed.decode('utf-8') if isinstance(hashed, bytes) else hashed


def check_password(plain_text_password, hashed_password):
    # Check hashed password. Using bcrypt, the salt is saved into the hash itself
    try:
        return bcrypt.checkpw(_as_bytes(plain_text_password),
                              _as_bytes(hashed_password))
    except (TypeError, UnicodeError):
        return bcrypt.checkpw(plain_text_password, hashed_password)
