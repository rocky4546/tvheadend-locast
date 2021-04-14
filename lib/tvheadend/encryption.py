import platform
import os
import logging

try:
    import cryptography
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.fernet import Fernet

    CRYPTO_LOADED = True
except ImportError:
    print('Unable to load cryptography module, will not encrypt passwords')
    CRYPTO_LOADED = False

ENCRYPT_STRING = 'ENC::'

LOGGER = logging.getLogger(__name__)


def set_fernet_key():
    opersystem = platform.system()
    # is there a key already generated
    if opersystem in ['Windows']:
        key_file = os.getenv('LOCALAPPDATA') + '/.locast/key.txt'
    else:  # linux
        key_file = os.getenv('HOME') + '/.locast/key.txt'
    try:
        with open(key_file, 'rb') as f:
            key = f.read()
    except FileNotFoundError:
        key = Fernet.generate_key()
        os.makedirs(os.path.dirname(key_file), exist_ok=True)
        with open(key_file, 'wb') as f:
            f.write(key)
    return key


def encrypt(clearstr, encrypt_key):
    if clearstr.startswith(ENCRYPT_STRING):
        # already encrypted_pwd
        return clearstr
    else:
        f = Fernet(encrypt_key)
        token = f.encrypt(clearstr.encode())
        return ENCRYPT_STRING + token.decode()


def decrypt(enc_str, encrypt_key):
    if enc_str.startswith(ENCRYPT_STRING):
        f = Fernet(encrypt_key)
        try:
            token = f.decrypt(enc_str[len(ENCRYPT_STRING):].encode())
        except cryptography.fernet.InvalidToken:
            # occurs when multiple users are running the app.
            # need to signal the caller that we have issues
            LOGGER.warning("Unable to decrypt string.")
            return None

        return token.decode()
    else:
        return enc_str
