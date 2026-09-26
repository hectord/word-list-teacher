# -*- coding: utf-8 -*-
#source: https://stackoverflow.com/questions/9594125/salt-and-hash-a-password-in-python

import bcrypt


def get_hashed_password(plain_text_password):
    # Hash a password for the first time
    #   (Using bcrypt, the salt is saved into the hash itself)
    if isinstance(plain_text_password, str):
        plain_text_password = plain_text_password.encode('utf-8')
    return bcrypt.hashpw(plain_text_password, bcrypt.gensalt()).decode('utf-8')

def check_password(plain_text_password, hashed_password):
    # Check hashed password. Using bcrypt, the salt is saved into the hash itself
    if isinstance(plain_text_password, str):
        plain_text_password = plain_text_password.encode('utf-8')
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')
    return bcrypt.checkpw(plain_text_password, hashed_password)
