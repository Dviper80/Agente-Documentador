<!-- Generado automaticamente por git-doc-agent. Ultima actualizacion: 2026-11-04T12:05:56.369935 -->

# Documentación Técnica del Proyecto: Git Doc Agent (GDA)

## 1. Descripción general

**Git Doc Agent (GDA)** es una herramienta automatizada diseñada para generar e integrar documentación técnica directamente a partir de la actividad de un repositorio Git. Su objetivo principal es simplificar y mantener al día el registro de cambios y la documentación de arquitectura del código sin interrumpir el flujo habitual de desarrollo del usuario.

El agente actúa interceptando eventos en el ciclo de vida de Git (como la confirmación de cambios mediante hooks) para analizar las modificaciones, generar un reporte documentado e integrarlo al historial sin requerir intervención manual constante.

---

## 2. Historial de evolución

| Fecha / Commit | Componentes afectados | Resumen del cambio |
| :--- | :--- | :--- |
| **2026-10-28**<br>`35478bc` | `doc_commit.py`<br>`install_hook.py`<br>`README.md` | **Soporte para `amend` automático y prevención de bucles en hooks**:<br>- Sustitución de `auto_stage` por `apply_git_action` para permitir integrar la documentación mediante `amend`, `commit`, `stage` o `none`.<br>- Introducción de la variable `GIT_DOC_AGENT_SKIP` para evitar la ejecución recursiva en hooks de Git. |

---

## 3. Componentes y módulos

```
+-------------------------------------------------------------+
|                      Git Repository                         |
+-------------------------------------------------------------+
                              |
                     (post-commit hook)
                              v
+-------------------------------------------------------------+
|                   scripts/install_hook.py                   |
|  - Inyecta la plantilla post-commit                         |
|  - Verifica GIT_DOC_AGENT_SKIP para abortar recursividad    |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                   scripts/doc_commit.py                     |
|  - Procesa los cambios del commit                           |
|  - Genera la documentación técnica                          |
|  - Ejecuta apply_git_action(modo)                           |
+-------------------------------------------------------------+
```

### 3.1. Generador de Documentación (`scripts/doc_commit.py`)
Es el script principal de la CLI. Se encarga de:
- Parsear los datos de los commits e invocar la generación de registros.
- Interpretar los argumentos de la línea de comandos (`--action`, `--no-stage`) y las variables de entorno.
- Aplicar la acción de Git correspondiente mediante la función `apply_git_action`.
- Inyectar marcas de control para evitar la reejecución en bucle.

### 3.2. Instalador y plantilla de Hooks (`scripts/install_hook.py`)
Encargado de configurar el entorno local de Git:
- Despliega la plantilla del hook `post-commit` en el directorio `.git/hooks/`.
- Inserta las comprobaciones de la variable de entorno `GIT_DOC_AGENT_SKIP` para detener prematuramente la ejecución del hook cuando el sistema está modificando automáticamente el repositorio.

### 3.3. Configuración y Documentación de Usuario (`README.md`)
Servicio de referencia para el usuario final donde se especifican las variables de entorno soportadas (como `GDA_COMMIT_ACTION`) y los modos de integración disponibles.

---

## 4. Decisiones de diseño

### 4.1. Modos flexibles de integración en Git (`apply_git_action`)
Para evitar llenar el historial de Git con commits secundarios no deseados o dejar archivos en estado "modificado" sin confirmar, se sustituyó la función rígida `auto_stage` por una estrategia orientada a políticas (`GDA_COMMIT_ACTION` / `--action`):

- **`amend` (Predeterminado)**: Fusiona la documentación generada dentro del commit actual (`git commit --amend --no-edit`). Esto mantiene el historial limpio, haciendo que la documentación y el código convivan en la misma entrada.
- **`commit`**: Crea un nuevo commit exclusivo para la documentación (`docs: auto-document commit <sha>`).
- **`stage`**: Simplemente añade la documentación al área de preparación (*staging area*) con `git add`.
- **`none`**: Genera el archivo sin realizar ninguna operación en Git.

### 4.2. Prevención de bucles infinitos en el hook `post-commit`
**Problema**: Al invocar comandos como `git commit` o `git commit --amend` desde dentro de un hook `post-commit`, Git vuelve a disparar el evento `post-commit`, creando una cadena de ejecuciones infinitas.

**Solución**: Se implementó una guardia mediante la variable de entorno `GIT_DOC_AGENT_SKIP`:
1. Cuando `doc_commit.py` ejecuta una acción de Git (`amend` o `commit`), inyecta `GIT_DOC_AGENT_SKIP="1"` en el entorno del subproceso.
2. Tanto `doc_commit.py` al inicio de su ejecución como la plantilla del hook `post-commit` (`install_hook.py`) verifican si esta variable vale `"1"`.
3. Si está presente, la ejecución aborta inmediatamente con un código de salida limpio (`exit 0`), rompiendo la recursividad.

### 4.3. Compatibilidad con versiones anteriores
Se mantuvo el flag `--no-stage` en la interfaz CLI, mapeándolo directamente a la acción `--action none` para asegurar que scripts o configuraciones previas sigan funcionando sin alteraciones.

---

## 5. Estado actual

### Funcionalidades implementadas
- [x] Generación de documentación basada en commits.
- [x] Interceptor mediante hook de Git (`post-commit`).
- [x] Soporte para múltiples estrategias de confirmación en Git (`amend`, `commit`, `stage`, `none`).
- [x] Mecanismo de seguridad anti-recursividad con `GIT_DOC_AGENT_SKIP`.
- [x] Configuración centralizada mediante la variable de entorno `GDA_COMMIT_ACTION`.

---

## 6. Guía de inicio rápido

### 6.1. Requisitos previos
- Entorno de ejecución Python 3.x.
- Repositorio Git inicializado.

### 6.2. Instalación del Hook
Para instalar el hook de documentación en tu repositorio local:

```bash
python scripts/install_hook.py
```

### 6.3. Configuración de uso
Puedes configurar el comportamiento predeterminado del agente definiendo la variable de entorno `GDA_COMMIT_ACTION`:

```bash
# Modo predeterminado: Fusiona la documentación en el mismo commit
export GDA_COMMIT_ACTION=amend

# Modo commit separado: Crea un commit independiente para la doc
export GDA_COMMIT_ACTION=commit

# Modo stage: Solo hace 'git add' del archivo generado
export GDA_COMMIT_ACTION=stage

# Modo ninguno: No toca Git
export GDA_COMMIT_ACTION=none
```

### 6.4. Ejecución manual
También se puede ejecutar el script directamente desde la CLI:

```bash
# Ejecutar usando el modo amend por defecto
python scripts/doc_commit.py

# Especificar un modo explícito
python scripts/doc_commit.py --action commit

# Ejecutar sin modificar el estado de Git
python scripts/doc_commit.py --no-stage
```

---

## 7. Glosario

- **`amend`**: Operación de Git (`git commit --amend`) que permite modificar la última confirmación realizada, agregando nuevos cambios o actualizando su mensaje.
- **`post-commit hook`**: Script ejecutable que Git lanza automáticamente justo después de que un commit se completa con éxito.
- **`Stage` / `Staging Area`**: Zona intermedia de Git donde se preparan los archivos antes de confirmar la versión (`git add`).
- **`GDA`**: *Git Doc Agent*, nombre de la herramienta.