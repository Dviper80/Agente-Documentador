#!/usr/bin/env python3
"""
setup_key.py - Guarda la GEMINI_API_KEY en ~/.gda_config.

El hook de git lee ese archivo directamente, lo que soluciona el problema
de que sh.exe de Git for Windows no hereda las variables de entorno de Windows.

Uso:
    python setup_key.py --key TU_CLAVE_AQUI
    python setup_key.py            # pide la clave de forma interactiva (oculta)
"""

import argparse
import getpass
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CONFIG_FILE = Path.home() / ".gda_config"

# IMPORTANTE: formato simple KEY=VALUE (sin 'export') para que
# Python lo lea facilmente en cualquier plataforma.
CONFIG_TEMPLATE = """\
# git-doc-agent config - generado por setup_key.py
# No editar manualmente.
GEMINI_API_KEY={api_key}
"""


def save_key(api_key: str):
    CONFIG_FILE.write_text(CONFIG_TEMPLATE.format(api_key=api_key), encoding="utf-8")
    try:
        CONFIG_FILE.chmod(0o600)  # Solo propietario en Linux/macOS
    except Exception:
        pass
    print(f"[setup_key] API key guardada en: {CONFIG_FILE}")
    print("[setup_key] El hook git la leera automaticamente en cada commit.")
    print()
    print("Verificacion: haz un commit en tu proyecto:")
    print("  cd /ruta/a/tu/proyecto")
    print("  git commit --allow-empty -m \"test: verificacion del hook\"")


def main():
    parser = argparse.ArgumentParser(description="Guarda la GEMINI_API_KEY para git-doc-agent.")
    parser.add_argument("--key", default=None, help="La API key de Gemini.")
    args = parser.parse_args()

    if args.key:
        api_key = args.key.strip()
    else:
        print("Introduce tu GEMINI_API_KEY (la entrada no se mostrara en pantalla):")
        api_key = getpass.getpass(prompt="  GEMINI_API_KEY: ").strip()

    if not api_key:
        print("[setup_key] ERROR: La API key no puede estar vacia.", file=sys.stderr)
        sys.exit(1)

    save_key(api_key)


if __name__ == "__main__":
    main()
