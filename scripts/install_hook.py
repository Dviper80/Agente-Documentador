#!/usr/bin/env python3
"""
install_hook.py - Instala el hook post-commit en un repositorio git.

Uso:
    python install_hook.py --repo-path C:\\ruta\\al\\proyecto
"""

import argparse
import stat
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# El hook carga ~/.gda_config con KEY=VALUE (sin 'export'),
# compatible tanto con sh del hook como con la lectura Python.
HOOK_TEMPLATE = """\
#!/bin/sh
# git-doc-agent -- post-commit hook (auto-generated)

GDA_SCRIPTS_DIR="{scripts_dir}"

# Cargar API key desde ~/.gda_config (generado por setup_key.py)
GDA_CONFIG="$HOME/.gda_config"
if [ -f "$GDA_CONFIG" ]; then
    while IFS='=' read -r key value; do
        case "$key" in
            \\#*|"") continue ;;
        esac
        export "$key=$value"
    done < "$GDA_CONFIG"
fi

# Resolver la raiz del repo de forma portable en Windows y Linux/macOS
REPO_ROOT=$(git rev-parse --show-toplevel)

# Detectar interprete de Python disponible
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD=python
else
    echo "[git-doc-agent] ERROR: No se encontro Python en el PATH." >&2
    exit 1
fi

# Ejecutar el documentador del commit actual
"$PYTHON_CMD" "$GDA_SCRIPTS_DIR/doc_commit.py" --repo-path "$REPO_ROOT" --commit HEAD

# Para regenerar la doc global en cada commit, descomenta la siguiente linea:
# "$PYTHON_CMD" "$GDA_SCRIPTS_DIR/doc_project.py" --repo-path "$REPO_ROOT"

exit 0
"""


def install(repo_path: str, scripts_dir: str):
    hook_dir = Path(repo_path) / ".git" / "hooks"
    if not hook_dir.exists():
        print(f"[install_hook] ERROR: No se encontro .git/hooks en {repo_path}")
        sys.exit(1)

    hook_file = hook_dir / "post-commit"

    if hook_file.exists():
        backup = hook_file.with_suffix(".pre-gda.bak")
        # Eliminar backup anterior si existe (Windows no permite overwrite con rename)
        if backup.exists():
            backup.unlink()
        hook_file.rename(backup)
        print(f"[install_hook] Hook anterior respaldado -> {backup.name}")

    hook_content = HOOK_TEMPLATE.format(scripts_dir=scripts_dir.replace("\\", "/"))
    hook_file.write_text(hook_content, encoding="utf-8")
    hook_file.chmod(hook_file.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    print(f"[install_hook] Hook instalado en: {hook_file}")
    print()
    print("Siguiente paso: guarda tu API key ejecutando:")
    print(f"  python \"{scripts_dir}/setup_key.py\" --key TU_CLAVE")


def main():
    parser = argparse.ArgumentParser(description="Instala el hook post-commit de git-doc-agent.")
    parser.add_argument("--repo-path", required=True, help="Ruta al repositorio git.")
    parser.add_argument("--scripts-dir", default=None, help="Ruta a scripts/. Default: dir de este script.")
    args = parser.parse_args()

    repo_path = str(Path(args.repo_path).resolve())
    scripts_dir = str(Path(args.scripts_dir or Path(__file__).parent).resolve())
    install(repo_path, scripts_dir)


if __name__ == "__main__":
    main()
