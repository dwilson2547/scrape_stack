from PIL import Image
import imagehash
import io
from typing import Optional

def compute_dhash(data: bytes) -> Optional[str]:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        h = imagehash.dhash(img)
        return str(h)
    except Exception:
        return None
