import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class BrokerTokenVault:
    """
    AES-256-GCM authenticated encryption vault for sensitive broker credentials.
    Guarantees access tokens are never stored in plaintext (Section 11 & Rule 3).
    """
    def __init__(self, key_base64: str | None = None):
        # 32 bytes key for AES-256
        raw_key = os.environ.get("ENCRYPTION_KEY_32BYTES_BASE64") or key_base64
        env = os.environ.get("ENVIRONMENT", "development").lower()
        is_dev = env in ["development", "dev", "test", "testing"]

        if raw_key:
            try:
                decoded = base64.b64decode(raw_key)
                if len(decoded) < 32:
                    if not is_dev:
                        raise RuntimeError(
                            "ENCRYPTION_KEY_32BYTES_BASE64 decoded key is shorter than required 32 bytes for AES-256."
                        )
                    self.key = decoded.ljust(32, b'0')
                else:
                    self.key = decoded[:32]
            except Exception as e:
                if not is_dev:
                    raise RuntimeError(f"Corrupt or invalid ENCRYPTION_KEY_32BYTES_BASE64: {e}") from e
                self.key = AESGCM.generate_key(bit_length=256)
        else:
            if not is_dev:
                raise RuntimeError(
                    "Critical Security Error: ENCRYPTION_KEY_32BYTES_BASE64 is missing in non-dev environment. "
                    "The broker token vault refuses to start with an ephemeral key."
                )
            self.key = AESGCM.generate_key(bit_length=256)
        self.aesgcm = AESGCM(self.key)

    def encrypt_token(self, plaintext: str) -> str:
        """Encrypt token and return base64 payload containing nonce + ciphertext."""
        nonce = os.urandom(12) # 96-bit nonce for AES-GCM
        ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode('utf-8')

    def decrypt_token(self, encrypted_b64: str) -> str:
        """Decrypt base64 ciphertext and return plaintext token."""
        raw = base64.b64decode(encrypted_b64.encode('utf-8'))
        nonce = raw[:12]
        ciphertext = raw[12:]
        decrypted = self.aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted.decode('utf-8')

token_vault = BrokerTokenVault()
