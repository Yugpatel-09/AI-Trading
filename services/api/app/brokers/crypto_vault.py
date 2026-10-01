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
        if raw_key:
            try:
                self.key = base64.b64decode(raw_key)[:32].ljust(32, b'0')
            except Exception:
                self.key = AESGCM.generate_key(bit_length=256)
        else:
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
