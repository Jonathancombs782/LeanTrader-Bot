import os

from cryptography.fernet import Fernet, InvalidToken


def _get_key_env() -> bytes:
    key = os.getenv("USER_SECRET_KEY")
    if not key:
        # Generate a transient key (NOT persistent). For production, provide a fixed base64 key in .env
        key = Fernet.generate_key().decode()
    return key.encode()


def get_cipher() -> Fernet:
    return Fernet(_get_key_env())


def encrypt_str(plain: str) -> str:
    c = get_cipher()
    return c.encrypt(plain.encode()).decode()


def decrypt_str(token: str) -> str:
    c = get_cipher()
    try:
        return c.decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
