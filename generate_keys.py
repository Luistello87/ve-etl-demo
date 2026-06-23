# generate_keys.py
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def generate_keypair():
    print("Generating RSA asymmetric keypair (2048-bit)...")
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    
    # Serialize private key to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption() # No password for easy local demo runs
    )
    
    # Save private key to file (Keep this secure!)
    with open("private_key.pem", "wb") as f:
        f.write(private_pem)
        
    # Extract and serialize public key to PEM format
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # Save public key to file (This is sent to the sender/shared)
    with open("public_key.pem", "wb") as f:
        f.write(public_pem)
        
    print("Keys successfully generated!")
    print(" - Private Key saved as: private_key.pem (Deploy on Laptop B - Receiver)")
    print(" - Public Key saved as:  public_key.pem  (Deploy on Laptop A - Sender)")

if __name__ == "__main__":
    generate_keypair()
