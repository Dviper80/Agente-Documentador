# git-doc-agent 🤖📄

**Agente documentador automático de proyectos Git usando IA (Gemini).**

Cada vez que hagas un `git commit`, este sistema:
1. Captura el diff del commit y lo envía a **Gemini Flash** (LLM #1) para generar una entrada de cambios en Markdown.
2. Opcionalmente (o bajo demanda), **Gemini Pro** (LLM #2) consolida todas las entradas en una documentación global del proyecto.

```
Tu proyecto/
├── .git/hooks/post-commit   ← hook instalado automáticamente
└── docs/
    ├── changes/
    │   ├── 2024-01-15_a1b2c3d4.md   ← LLM #1 genera uno por commit
    │   ├── 2024-01-16_e5f6g7h8.md
    │   └── ...
    └── PROJECT_DOCUMENTATION.md     ← LLM #2 consolida todo aquí
```

---

## ⚡ Instalación rápida

### Opción 1: Instalar directamente con `pip` (Recomendada en cualquier equipo)

Puedes instalar la herramienta y sus comandos de consola directamente desde GitHub sin necesidad de clonar manualmente:

```bash
pip install git+https://github.com/Dviper80/Agente-Documentador.git
```

O si prefieres añadirlo a las dependencias de tu proyecto (`requirements.txt`):
```text
git+https://github.com/Dviper80/Agente-Documentador.git
```

Una vez instalado, dispones de los comandos globales `gda-setup`, `gda-install`, `gda-project` y `gda-commit`.

---

### Opción 2: Clonando el repositorio

```bash
git clone https://github.com/Dviper80/Agente-Documentador.git
cd Agente-Documentador
pip install -r requirements.txt
```

---

### Configuración inicial (3 pasos)

#### 1. Configurar tu API Key de Gemini
Obtén una clave gratuita en [Google AI Studio](https://aistudio.google.com/app/apikey) y guárdala:

```bash
# Con CLI global:
gda-setup --key TU_API_KEY

# O con script directo:
python scripts/setup_key.py --key TU_API_KEY
```

#### 2. Instalar el hook en tu repositorio objetivo

```bash
# Con CLI global:
gda-install --repo-path /ruta/a/tu-proyecto

# O con script directo:
python scripts/install_hook.py --repo-path /ruta/a/tu-proyecto
```

#### 3. ¡Listo! Haz un commit en tu proyecto
```bash
cd /ruta/a/tu-proyecto
git add .
git commit -m "feat: mi primer commit documentado"
# → Agente-Documentador genera docs/changes/YYYY-MM-DD_<sha>.md automáticamente
```

---

## 📋 Uso

### Documentar un commit manualmente

```bash
python scripts/doc_commit.py --repo-path /ruta/proyecto --commit HEAD
python scripts/doc_commit.py --repo-path /ruta/proyecto --commit abc1234
```

### Generar/actualizar la documentación global del proyecto

```bash
python scripts/doc_project.py --repo-path /ruta/proyecto
# Genera docs/PROJECT_DOCUMENTATION.md consolidando todos los changes/*.md
```

### Documentar commits históricos

```bash
# Documentar los últimos 10 commits
git -C /ruta/proyecto log --oneline -10 | while read sha msg; do
    python scripts/doc_commit.py --repo-path /ruta/proyecto --commit $sha --no-stage
done

# Luego consolidar
python scripts/doc_project.py --repo-path /ruta/proyecto
```

---

## ⚙️ Configuración

Todas las opciones se controlan mediante **variables de entorno**:

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `GEMINI_API_KEY` | **Requerida.** Tu clave de API de Gemini | — |
| `GDA_COMMIT_ACTION` | Modo de guardado Git: `amend` (mismo commit), `commit` (commit propio), `stage` o `none` | `amend` |
| `GDA_COMMIT_MODEL` | Modelo para documentar commits | `gemini-3.5-flash` |
| `GDA_PROJECT_MODEL` | Modelo para documentación global | `gemini-3.5-flash` |
| `GDA_CHANGES_DIR` | Subcarpeta de cambios (relativa al repo) | `docs/changes` |
| `GDA_OUTPUT_DOC` | Archivo de documentación global | `docs/PROJECT_DOCUMENTATION.md` |
| `GDA_MAX_RETRIES` | Reintentos por saturación o límites (503/429) | `3` |
| `GDA_RETRY_DELAY` | Segundos de espera entre reintentos | `5` |
| `GDA_MAX_DIFF_CHARS` | Tamaño máximo del diff enviado a la IA | `40000` |
| `GDA_MAX_INPUT_CHARS` | Tamaño máximo de entrada al LLM #2 | `200000` |

Ejemplo en PowerShell:

```powershell
$env:GEMINI_API_KEY   = "tu-clave"
$env:GDA_COMMIT_MODEL = "gemini-2.0-flash"
$env:GDA_PROJECT_MODEL = "gemini-1.5-pro"
```

---

## 🏗️ Arquitectura

```
git commit
    │
    ▼
post-commit hook
    │
    ▼
doc_commit.py
    ├── git show → obtiene diff + metadatos
    ├── LLM #1 (Gemini Flash) → redacta cambios en Markdown
    └── Guarda en docs/changes/<fecha>_<sha>.md
            │
            ▼ (bajo demanda)
        doc_project.py
            ├── Lee todos los docs/changes/*.md
            ├── LLM #2 (Gemini Pro) → consolida en documentación global
            └── Guarda en docs/PROJECT_DOCUMENTATION.md
```

---

## 💡 Consejos

- **Commitea los docs generados**: los archivos `docs/changes/*.md` y `docs/PROJECT_DOCUMENTATION.md` pueden incluirse en el repositorio para que todo el equipo los vea.
- **`.gitignore` selectivo**: si prefieres no commitear los changes individuales, añade `docs/changes/` a `.gitignore` pero mantén `docs/PROJECT_DOCUMENTATION.md`.
- **Regenerar la doc global tras varios commits**: ejecuta `doc_project.py` manualmente o añádelo como un paso en tu CI/CD.
- **Diffs grandes**: el hook omite automáticamente diffs que superen `GDA_MAX_DIFF_CHARS`. Ajusta según el límite de tokens de tu modelo.

---

## 🧪 Pruebas automatizadas

Para verificar el correcto funcionamiento de todo el sistema (incluyendo la resolución de intérprete en hooks, lectura de claves y generación):

```bash
python -m unittest discover tests
```

---

## 📁 Estructura del proyecto

```
Agente-Documentador/
├── .gitignore         ← exclusiones de git (claves, temporales, venvs)
├── pyproject.toml     ← empaquetado pip y comandos CLI (gda-*)
├── requirements.txt   ← dependencias de Python (google-genai)
├── README.md          ← esta guía
├── scripts/
│   ├── __init__.py     ← inicializador de módulo Python
│   ├── doc_commit.py   ← LLM #1: documenta un commit individual
│   ├── doc_project.py  ← LLM #2: consolida la documentación global
│   ├── install_hook.py ← instala el git hook post-commit en cualquier repo
│   └── setup_key.py    ← guarda la API key de forma persistente y portable
└── tests/
    ├── __init__.py     ← paquete de tests
    └── test_agent.py   ← suite completa de pruebas unitarias y e2e
```
