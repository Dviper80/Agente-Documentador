#!/usr/bin/env python3
"""
doc_project.py - LLM #2: Consolida todos los cambios en documentacion global.

Uso:
    python doc_project.py [--repo-path PATH] [--output PATH]
"""

import argparse
import os
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
GEMINI_MODEL_PROJECT = os.getenv("GDA_PROJECT_MODEL", "gemini-3.5-flash")
# Modelos de fallback en orden (se usan si el principal da 503/504)
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
MAX_RETRIES = int(os.getenv("GDA_MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("GDA_RETRY_DELAY", "5"))  # segundos entre reintentos
DOCS_CHANGES_SUBDIR = os.getenv("GDA_CHANGES_DIR", "docs/changes")
DEFAULT_OUTPUT = os.getenv("GDA_OUTPUT_DOC", "docs/PROJECT_DOCUMENTATION.md")
MAX_INPUT_CHARS = int(os.getenv("GDA_MAX_INPUT_CHARS", "200000"))

PROMPT_TEMPLATE = textwrap.dedent("""\
    Eres un arquitecto de software y documentador tecnico experto.

    Se te proporcionan {n} entradas de cambios de un proyecto de software, cada
    una generada automaticamente a partir de un commit de Git. Tu tarea es
    sintetizarlas en una **documentacion tecnica completa del proyecto** en Markdown.

    La documentacion debe incluir:
    1. **Descripcion general**: que hace el proyecto, su proposito y arquitectura.
    2. **Historial de evolucion**: linea de tiempo resumida agrupando cambios tematicamente.
    3. **Componentes y modulos**: descripcion de los componentes principales y sus relaciones.
    4. **Decisiones de diseno**: patrones y decisiones tecnicas relevantes detectadas.
    5. **Estado actual**: funcionalidades implementadas, en progreso o refactorizadas.
    6. **Guia de inicio rapido** (si hay suficiente informacion).
    7. **Glosario** (opcional): terminos del dominio mencionados.

    Responde UNICAMENTE con el Markdown del documento, comenzando por el titulo.

    ---
    **Entradas de cambios ({n} commits documentados)**

    {entries}
""")


def load_api_key() -> str:
    """Carga la API key desde la variable de entorno o desde ~/.gda_config."""
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return api_key

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
        "  Ejecuta: python scripts/setup_key.py --key TU_CLAVE",
        file=sys.stderr,
    )
    sys.exit(1)


def load_change_entries(changes_dir: Path) -> list:
    if not changes_dir.exists():
        print(f"[git-doc-agent] No se encontro el directorio: {changes_dir}", file=sys.stderr)
        return []
    files = sorted(changes_dir.glob("*.md"))
    if not files:
        print(f"[git-doc-agent] No hay archivos en {changes_dir}", file=sys.stderr)
        return []
    entries = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            entries.append({"file": f.name, "content": content})
        except OSError as e:
            print(f"[git-doc-agent] No se pudo leer {f.name}: {e}", file=sys.stderr)
    print(f"[git-doc-agent] Cargadas {len(entries)} entradas de cambios.")
    return entries


def build_input(entries: list) -> str:
    parts = [f"### Entrada {i}: {e['file']}\n\n{e['content']}" for i, e in enumerate(entries, 1)]
    combined = "\n\n---\n\n".join(parts)
    if len(combined) > MAX_INPUT_CHARS:
        combined = combined[:MAX_INPUT_CHARS] + "\n\n[... contenido truncado ...]"
    return combined


def generate_project_doc(entries: list) -> str:
    # Forzar uso del endpoint de Google AI Studio (no Vertex AI)
    os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    client = genai.Client(api_key=load_api_key())
    combined = build_input(entries)
    prompt = PROMPT_TEMPLATE.format(n=len(entries), entries=combined)

    # Lista de modelos a intentar (el configurado + fallbacks)
    preferred = os.getenv("GDA_PROJECT_MODEL", GEMINI_MODEL_PROJECT)
    models_to_try = [preferred] + [m for m in FALLBACK_MODELS if m != preferred]

    for model in models_to_try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"[git-doc-agent] Generando doc global con {model} (intento {attempt}/{MAX_RETRIES})...")
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
                    # Error no recuperable (404, 401, etc.) — saltar al siguiente modelo
                    print(f"[git-doc-agent] Error con {model}: {err[:100]}")
                    break

    print("[git-doc-agent] ERROR: Todos los modelos fallaron.", file=sys.stderr)
    sys.exit(1)


def save_project_doc(repo_path: str, content: str, output_rel: str) -> Path:
    output_file = Path(repo_path) / output_rel
    output_file.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"<!-- Generado automaticamente por git-doc-agent. "
        f"Ultima actualizacion: {datetime.now().isoformat()} -->\n\n"
    )
    output_file.write_text(header + content, encoding="utf-8")
    print(f"[git-doc-agent] Documentacion global -> {output_file.relative_to(repo_path)}")
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Consolida cambios en documentacion global.")
    parser.add_argument("--repo-path", default=".", help="Ruta al repositorio git.")
    parser.add_argument("--output", default=None, help=f"Archivo de salida. Default: {DEFAULT_OUTPUT}")
    args = parser.parse_args()

    repo_path = str(Path(args.repo_path).resolve())
    output_rel = args.output or DEFAULT_OUTPUT
    changes_dir = Path(repo_path) / DOCS_CHANGES_SUBDIR
    entries = load_change_entries(changes_dir)

    if not entries:
        print("[git-doc-agent] Nada que consolidar. Saliendo.")
        sys.exit(0)

    content = generate_project_doc(entries)
    save_project_doc(repo_path, content, output_rel)


if __name__ == "__main__":
    main()
