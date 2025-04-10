import secrets
import hashlib
import base64

def generate_pkce_verifier(length: int = 64) -> str:
    """Generates a high-entropy cryptographic random string for PKCE."""
    if not (43 <= length <= 128):
        raise ValueError("Verifier length must be between 43 and 128 characters.")
    # Generate random bytes and encode them using URL-safe base64 without padding
    verifier_bytes = secrets.token_bytes(length)
    verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b'=').decode('utf-8')
    # Ensure the verifier is within the length limits (rare edge case with encoding)
    return verifier[:length]

def calculate_pkce_challenge(verifier: str) -> str:
    """Calculates the S256 PKCE code challenge from the verifier."""
    # Hash the verifier using SHA-256
    sha256_hash = hashlib.sha256(verifier.encode('utf-8')).digest()
    # Encode the hash using URL-safe base64 without padding
    challenge = base64.urlsafe_b64encode(sha256_hash).rstrip(b'=').decode('utf-8')
    return challenge

# Example usage:
# verifier = generate_pkce_verifier()
# challenge = calculate_pkce_challenge(verifier)
# print(f"Verifier: {verifier}")
# print(f"Challenge: {challenge}") 