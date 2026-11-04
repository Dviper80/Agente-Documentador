#!/usr/bin/env python3
"""
test_agent.py - Suite de pruebas para git-doc-agent.
Verifica:
1. Configuracion y lectura de API keys (prioridad de entorno, local y global).
2. Instalacion del hook de Git y respaldos.
3. Extraccion de metadatos y diffs de commits Git.
4. Generacion y guardado de archivos de documentacion (commit y proyecto).
5. Acciones Git automaticas (amend, stage, commit).
6. Prueba de integracion completa end-to-end con un commit real de Git.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Asegurar que la raiz del proyecto este en sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import doc_commit, doc_project, install_hook, setup_key


class TestSetupKeyAndLoadKey(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="gda_test_key_")
        self.temp_path = Path(self.temp_dir)
        self.original_env = os.environ.get("GEMINI_API_KEY")

    def tearDown(self):
        if self.original_env is not None:
            os.environ["GEMINI_API_KEY"] = self.original_env
        else:
            os.environ.pop("GEMINI_API_KEY", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_key_file(self):
        test_file = self.temp_path / ".gda_config"
        test_key = "AIzaSyTestKey_12345"
        setup_key.save_key(test_key, dest_path=test_file)

        self.assertTrue(test_file.exists())
        content = test_file.read_text(encoding="utf-8")
        self.assertIn(f"GEMINI_API_KEY={test_key}", content)
        # Asegurar terminacion LF para compatibilidad con sh/bash
        self.assertNotIn("\r\n", content)

    def test_load_key_precedence_env(self):
        os.environ["GEMINI_API_KEY"] = "key_from_env"
        # Debe priorizar la variable de entorno
        key = doc_commit.load_api_key(repo_path=str(self.temp_path))
        self.assertEqual(key, "key_from_env")

    def test_load_key_local_repo(self):
        os.environ.pop("GEMINI_API_KEY", None)
        local_config = self.temp_path / ".gda_config"
        local_config.write_text("GEMINI_API_KEY=key_from_local\n", encoding="utf-8")

        key = doc_commit.load_api_key(repo_path=str(self.temp_path))
        self.assertEqual(key, "key_from_local")

    def test_load_key_strips_carriage_return(self):
        # Simular lectura con retorno de carro (\r\n)
        os.environ.pop("GEMINI_API_KEY", None)
        local_config = self.temp_path / ".gda_config"
        local_config.write_bytes(b"GEMINI_API_KEY=key_with_cr\r\n")

        key = doc_commit.load_api_key(repo_path=str(self.temp_path))
        self.assertEqual(key, "key_with_cr")


class TestInstallHook(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="gda_test_hook_")
        self.repo_path = Path(self.temp_dir)
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_install_creates_executable_hook(self):
        scripts_dir = str(PROJECT_ROOT / "scripts")
        install_hook.install(str(self.repo_path), scripts_dir, sys.executable)

        hook_file = self.repo_path / ".git" / "hooks" / "post-commit"
        self.assertTrue(hook_file.exists())

        content = hook_file.read_text(encoding="utf-8")
        self.assertIn("GDA_SCRIPTS_DIR=", content)
        self.assertIn("run_python", content)
        self.assertIn("tr -d '\\r'", content)
        # Asegurar LF
        self.assertNotIn("\r\n", content)

    def test_install_creates_backup_of_existing_hook(self):
        hook_file = self.repo_path / ".git" / "hooks" / "post-commit"
        hook_file.write_text("#!/bin/sh\n# Old hook\n", encoding="utf-8")

        scripts_dir = str(PROJECT_ROOT / "scripts")
        install_hook.install(str(self.repo_path), scripts_dir, sys.executable)

        backup_file = self.repo_path / ".git" / "hooks" / "post-commit.pre-gda.bak"
        self.assertTrue(backup_file.exists())
        self.assertEqual(backup_file.read_text(encoding="utf-8"), "#!/bin/sh\n# Old hook\n")


class TestGitMetadataAndDiff(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="gda_test_git_")
        self.repo_path = Path(self.temp_dir)
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Author"], cwd=self.repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@domain.com"], cwd=self.repo_path, check=True)

        # Crear un archivo y hacer commit
        test_file = self.repo_path / "module.py"
        test_file.write_text("def salute():\n    return 'Hello'\n", encoding="utf-8")
        subprocess.run(["git", "add", "module.py"], cwd=self.repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "feat: create salute function"], cwd=self.repo_path, check=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_commit_info(self):
        sha = doc_commit.run_git(["rev-parse", "HEAD"], str(self.repo_path))
        info = doc_commit.get_commit_info(sha, str(self.repo_path))

        self.assertEqual(info["sha"], sha)
        self.assertIn("Test Author", info["author"])
        self.assertIn("test@domain.com", info["author"])
        self.assertEqual(info["message"], "feat: create salute function")

    def test_get_diff(self):
        sha = doc_commit.run_git(["rev-parse", "HEAD"], str(self.repo_path))
        diff = doc_commit.get_diff(sha, str(self.repo_path))

        self.assertIn("module.py", diff)
        self.assertIn("def salute()", diff)


class TestSaveDocAndGitActions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="gda_test_actions_")
        self.repo_path = Path(self.temp_dir)
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Author"], cwd=self.repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@domain.com"], cwd=self.repo_path, check=True)

        (self.repo_path / "file.txt").write_text("version 1", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=self.repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=self.repo_path, check=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_doc(self):
        sha = doc_commit.run_git(["rev-parse", "HEAD"], str(self.repo_path))
        info = {
            "sha": sha,
            "author": "Test Author <test@domain.com>",
            "date": "2026-11-04 12:00:00",
            "message": "test save doc",
        }
        content = "# Resumen de Cambios\nSe agrego funcionalidad."
        saved_file = doc_commit.save_doc(str(self.repo_path), info, content)

        self.assertTrue(saved_file.exists())
        saved_text = saved_file.read_text(encoding="utf-8")
        self.assertIn(f"commit: {sha}", saved_text)
        self.assertIn("Resumen de Cambios", saved_text)

    def test_apply_git_action_amend(self):
        sha = doc_commit.run_git(["rev-parse", "HEAD"], str(self.repo_path))
        info = {
            "sha": sha,
            "author": "Test Author <test@domain.com>",
            "date": "2026-11-04 12:00:00",
            "message": "test save doc",
        }
        saved_file = doc_commit.save_doc(str(self.repo_path), info, "# Doc")
        doc_commit.apply_git_action(str(self.repo_path), saved_file, action="amend", sha=sha)

        # Verificar que el commit actual contenga el archivo generado
        status = subprocess.run(["git", "show", "--stat", "HEAD"], cwd=self.repo_path, capture_output=True, text=True)
        self.assertIn(saved_file.name, status.stdout)


class TestDocProjectConsolidation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="gda_test_proj_")
        self.repo_path = Path(self.temp_dir)
        self.changes_dir = self.repo_path / "docs" / "changes"
        self.changes_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_entries_and_build_input(self):
        (self.changes_dir / "2026-11-01_11111111.md").write_text("# Doc 1\nDetalle 1", encoding="utf-8")
        (self.changes_dir / "2026-11-02_22222222.md").write_text("# Doc 2\nDetalle 2", encoding="utf-8")

        entries = doc_project.load_change_entries(self.changes_dir)
        self.assertEqual(len(entries), 2)

        combined = doc_project.build_input(entries)
        self.assertIn("Doc 1", combined)
        self.assertIn("Doc 2", combined)

    def test_save_project_doc(self):
        content = "# Documentacion Global del Proyecto\nArquitectura y modulos."
        out = doc_project.save_project_doc(str(self.repo_path), content, "docs/PROJECT_DOCUMENTATION.md")

        self.assertTrue(out.exists())
        text = out.read_text(encoding="utf-8")
        self.assertIn("Documentacion Global", text)
        self.assertIn("Generado automaticamente por git-doc-agent", text)


class TestEndToEndHookExecution(unittest.TestCase):
    """
    Prueba de integracion completa:
    Instala el hook en un repo real, hace un commit y verifica
    que el hook ejecute y genere la documentacion.
    """
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="gda_e2e_")
        self.repo_path = Path(self.temp_dir)
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Integration Tester"], cwd=self.repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=self.repo_path, check=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_git_commit(self):
        # 1. Instalar el hook
        scripts_dir = str(PROJECT_ROOT / "scripts")
        install_hook.install(str(self.repo_path), scripts_dir, sys.executable)

        # 2. Mockear la llamada LLM si no hay API key real accesible en el test
        # O usar la real si esta disponible.
        # Creamos un archivo nuevo y commiteamos
        (self.repo_path / "service.py").write_text("class Service:\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "service.py"], cwd=self.repo_path, check=True)

        res = subprocess.run(
            ["git", "commit", "-m", "feat: add basic service class"],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )

        # Verificamos que la ejecucion de Git no fallo por stubs de Python
        self.assertNotIn("Python was not found", res.stderr)
        self.assertEqual(res.returncode, 0)

        # Verificamos que se haya generado el archivo en docs/changes
        changes_dir = self.repo_path / "docs" / "changes"
        self.assertTrue(changes_dir.exists(), f"El directorio docs/changes debio ser creado. Output: {res.stdout}\nStderr: {res.stderr}")
        generated_files = list(changes_dir.glob("*.md"))
        self.assertGreaterEqual(len(generated_files), 1, "Debio haberse generado al menos un archivo .md")

        # Verificamos que el archivo generado se incluyo en el commit via amend
        log_res = subprocess.run(["git", "log", "--stat", "-n", "1"], cwd=self.repo_path, capture_output=True, text=True)
        self.assertIn("docs/changes/", log_res.stdout)


if __name__ == "__main__":
    unittest.main()

