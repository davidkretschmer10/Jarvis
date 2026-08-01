from __future__ import annotations

import shutil
import subprocess
import logging

LOGGER = logging.getLogger(__name__)


def check_tesseract() -> tuple[bool, str]:
    """
    Checks if Tesseract OCR is installed and accessible.
    Returns (True, 'Připraveno (v...)') or (False, 'Chybí Tesseract').
    """
    # 1. Try pytesseract version check
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        return True, f"Připraveno (v{version})"
    except Exception as e:
        LOGGER.debug("pytesseract.get_tesseract_version failed: %s", e)

    # 2. Check path using shutil
    path = shutil.which("tesseract")
    if path:
        try:
            res = subprocess.run(
                ["tesseract", "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            if res.returncode == 0:
                version = "připraveno"
                for line in res.stdout.splitlines():
                    if "tesseract" in line.lower():
                        version = line.strip()
                        break
                return True, f"Připraveno ({version})"
        except Exception as e:
            LOGGER.debug("tesseract execution failed: %s", e)

    return False, "Chybí Tesseract"
