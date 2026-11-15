import os
import sys

# Ensure backend folder and root directory are in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(root_dir, "backend")

if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Vercel busca la variable "app" en este archivo: el import no está "sin usar"
from backend.app import app  # noqa: E402, F401

__all__ = ["app"]

