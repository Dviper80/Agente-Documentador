 #!/usr/bin/env python3
"""
doc_commit.py - LLM #1: Documenta un commit individual.

Uso (llamado automaticamente por el git hook post-commit):
    python doc_commit.py [--repo-path PATH] [--commit SHA]
"""

import argparse
import os
import subprocess
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path

# UTF-8 en consola Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from google import genai

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------
GEMINI_MODEL_COMMIT = os.getenv("GDA_COMMIT_MODEL", "gemini-3.5-flash")
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
MAX_RETRIES = int(os.getenv("GDA_MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("GDA_RETRY_DELAY", "5"))
DOCS_CHANGES_SUBDIR = os.getenv("GDA_CHANGES_DIR", "docs/changes")
MAX_DIFF_CHARS = int(os.getenv("GDA_MAX_DIFF_CHARS", "40000"))

PROMPT_TEMPLATE = textwrap.dedent("""\
    Eres un experto en documentacion tecnica de software.

    Se te proporciona el diff de un commit de Git. Tu tarea es redactar una
    entrada de cambios clara, detallada y bien estructurada en **Markdown**.

    El bloque debe contener:
    - **Resumen ejecutivo** (1-2 frases) de que cambio y por que.
    - **Archivos modificados**: lista con una linea descriptiva por archivo.
    - **Detalles tecnicos**: explica brevemente el "que" y el "porque" de los
      cambios mas relevantes (logica nueva, refactors, correcciones de bugs...).
    - **Impacto**: posibles efectos en otras partes del proyecto.

    Responde UNICAMENTE con el Markdown, sin preambulos ni explicaciones fuera
    del documento.

    ---
    **Metadatos del commit**
    - SHA: {sha}
    - Autor: {author}
    - Fecha: {date}
    - Mensaje: {message}

    **Diff**
    ```diff
    {diff}
    ```
""")


def load_api_key() -> str:
    """Carga la API key desde la variable de entorno o desde ~/.gda_config."""
    # 1. Variable de entorno directa
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return api_key

    # 2. Fallback: archivo ~/.gda_config (escrito por setup_key.py)
    config_file = Path.home() / ".gda_config"
    if config_file.exists():
        for line in config_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value

    print(
        "[git-doc-agent] ERROR: GEMINI_API_KEY no encontrada.\n"
        "  Ejecuta: python scripts/setup_key.py --key TU_CLAVE\n"
        "  O define: $env:GEMINI_API_KEY = 'tu-clave'",
        file=sys.stderr,
    )
    sys.exit(1)


def run_git(args: list, cwd: str) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        print(f"[git-doc-agent] git error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_commit_info(sha: str, repo_path: str) -> dict:
    fmt = "%H|%an <%ae>|%ad|%s"
    raw = run_git(["show", "-s", f"--format={fmt}", "--date=iso", sha], repo_path)
    parts = raw.split("|", 3)
    return {
        "sha": parts[0],
        "author": parts[1],
        "date": parts[2],
        "message": parts[3] if len(parts) > 3 else "",
    }


def get_diff(sha: str, repo_path: str) -> str:
    diff = run_git(["show", "--stat", "--patch", sha], repo_path)
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n[... diff truncado por tamano ...]"
    return diff


def generate_doc(info: dict, diff: str) -> str:
    # Forzar uso del endpoint de Google AI Studio (no Vertex AI)
    os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    client = genai.Client(api_key=load_api_key())
    prompt = PROMPT_TEMPLATE.format(
        sha=info["sha"],
        author=info["author"],
        date=info["date"],
        message=info["message"],
        diff=diff,
    )

    preferred = os.getenv("GDA_COMMIT_MODEL", GEMINI_MODEL_COMMIT)
    models_to_try = [preferred] + [m for m in FALLBACK_MODELS if m != preferred]

    for model in models_to_try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"[git-doc-agent] Generando doc para commit {info['sha'][:8]} con {model} (intento {attempt}/{MAX_RETRIES})...")
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                print(f"[git-doc-agent] Exito con modelo: {model}")
                return response.text
            except Exception as e:
                err = str(e)
                if "503" in err or "UNAVAILABLE" in err or "429" in err or "RESOURCE_EXHAUSTED" in err or "overloaded" in err.lower():
                    if attempt < MAX_RETRIES:
                        print(f"[git-doc-agent] {model} saturado o con límite de tasa, reintentando en {RETRY_DELAY}s...")
                        time.sleep(RETRY_DELAY)
                    else:
                        print(f"[git-doc-agent] {model} no disponible tras {MAX_RETRIES} intentos, probando siguiente modelo...")
                else:
                    print(f"[git-doc-agent] Error con {model}: {err[:100]}")
                    break

    print("[git-doc-agent] ERROR: Todos los modelos fallaron para el commit.", file=sys.stderr)
    sys.exit(1)


def save_doc(repo_path: str, info: dict, content: str) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    sha8 = info["sha"][:8]
    filename = f"{date_str}_{sha8}.md"

    output_dir = Path(repo_path) / DOCS_CHANGES_SUBDIR
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / filename
    header = textwrap.dedent(f"""\
        ---
        commit: {info['sha']}
        author: {info['author']}
        date: {info['date']}
        message: "{info['message']}"
        generated_at: {datetime.now().isoformat()}
        ---

    """)
    output_file.write_text(header + content, encoding="utf-8")
    print(f"[git-doc-agent] Guardado -> {output_file.relative_to(repo_path)}")
    return output_file


def auto_stage(repo_path: str, file: Path):
    rel = str(file.relative_to(repo_path)).replace("\\", "/")
    subprocess.run(["git", "add", rel], cwd=repo_path)


def main():
    parser = argparse.ArgumentParser(description="Documenta un commit con Gemini.")
    parser.add_argument("--repo-path", default=".", help="Ruta al repositorio git.")
    parser.add_argument("--commit", default="HEAD", help="SHA del commit (default: HEAD).")
    parser.add_argument("--no-stage", action="store_true", help="No hacer git add del archivo.")
    args = parser.parse_args()

    repo_path = str(Path(args.repo_path).resolve())
    sha = run_git(["rev-parse", args.commit], repo_path)
    info = get_commit_info(sha, repo_path)
    diff = get_diff(sha, repo_path)
    content = generate_doc(info, diff)
    doc_file = save_doc(repo_path, info, content)

    if not args.no_stage:
        auto_stage(repo_path, doc_file)


if __name__ == "__main__":
    main()
