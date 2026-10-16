"""
IgnisAI - Cifrado simétrico de credenciales sensibles.
La Contraseña de Aplicación de Google (HU06) se guarda cifrada en la base
de datos, nunca en texto plano. La clave de cifrado se genera una única
vez y se conserva localmente en disco (fuera del control de versiones).
"""
import os
import stat

from cryptography.fernet import Fernet, InvalidToken

import config

_KEY_PATH = os.path.join(config.BASE_DIR, ".secret.key")


def _load_or_create_key() -> bytes:
    if os.path.exists(_KEY_PATH):
        with open(_KEY_PATH, "rb") as f:
            return f.read().strip()
    key = Fernet.generate_key()
    with open(_KEY_PATH, "wb") as f:
        f.write(key)
    try:
        os.chmod(_KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)  # solo el propietario (600)
    except OSError:
        pass
    return key


def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def encrypt(plain_text: str) -> str:
    """Cifra una cadena de texto y devuelve un token seguro para almacenar."""
    if not plain_text:
        return ""
    return _fernet().encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Descifra un token previamente generado con `encrypt`. Devuelve '' si
    el token está vacío, corrupto o fue cifrado con otra clave."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
