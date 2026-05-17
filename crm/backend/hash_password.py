"""
Utilitaire pour générer le hash bcrypt d'un mot de passe.
Usage : python hash_password.py <mot_de_passe>
Copier le résultat dans .env : ADMIN_PASSWORD_HASH=<hash>
"""
import sys
from passlib.context import CryptContext

if len(sys.argv) != 2:
    print("Usage: python hash_password.py <mot_de_passe>")
    sys.exit(1)

ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
print(ctx.hash(sys.argv[1]))
