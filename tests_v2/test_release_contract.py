"""Cross-check release metadata and an installed wheel's real resources."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile

from cvanalysis import __version__


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = (
    'cvanalysis/default_themes.json',
    'cvanalysis/resources/icons/cvanalysis.ico',
    'cvanalysis/ui/glass/PyGlass-LICENSE',
    'cvanalysis/ui/glass/PyGlass-NOTICE.md',
)


def test_release_version_metadata_agrees():
    metadata = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    citation = (ROOT / 'CITATION.cff').read_text(encoding='utf-8')
    script = (ROOT / 'build.bat').read_text(encoding='utf-8')
    citation_version = re.search(r'^version:\s*(\S+)', citation, re.MULTILINE).group(1)
    default_build_version = re.search(r'if "%APP_VERSION%"=="" set "APP_VERSION=([^"]+)"', script).group(1)
    assert metadata['project']['version'] == citation_version == default_build_version == __version__


def test_installed_wheel_contains_and_loads_runtime_resources(tmp_path):
    # Build outside the working tree: setuptools must not leave build/egg-info
    # behind or accidentally pick up local settings or measurement files.
    source = tmp_path / 'source'
    source.mkdir()
    shutil.copytree(ROOT / 'cvanalysis', source / 'cvanalysis',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('pyproject.toml', 'README.md', 'LICENSE'):
        shutil.copy2(ROOT / name, source / name)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    built = subprocess.run(
        [sys.executable, '-c', "import setuptools.build_meta as b; b.build_wheel('dist')"],
        cwd=source, env=env, capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=90,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    wheels = list((source / 'dist').glob('*.whl'))
    assert len(wheels) == 1
    installed = tmp_path / 'installed'
    with zipfile.ZipFile(wheels[0]) as wheel:
        for name in RESOURCES:
            assert wheel.read(name) == (ROOT / name).read_bytes(), name
        wheel.extractall(installed)
    # -I prevents the checkout/CWD or PYTHONPATH from masking missing wheel data.
    smoke = subprocess.run(
        [sys.executable, '-I', '-c',
         "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
         "import cvanalysis; from cvanalysis.appearance import load_themes; "
         "from importlib.resources import files; from PIL import Image; "
         "assert Path(cvanalysis.__file__).resolve().is_relative_to(Path(sys.argv[1])); "
         "assert cvanalysis.__version__ == sys.argv[2]; "
         "assert {'default', 'kon'} <= {t.id for t in load_themes()}; "
         "icon = Image.open(files('cvanalysis').joinpath('resources/icons/cvanalysis.ico')); "
         "assert (256, 256) in icon.info['sizes']; icon.load(); icon.close()",
         str(installed), __version__],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=30,
    )
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
