"""Empacota somente os entregáveis; exclui ferramentas, logs e caches."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]

def main():
    target = ROOT / 'pet-aurora.zip'
    with ZipFile(target,'w',ZIP_DEFLATED) as archive:
        for name in ['README.md','.gitignore','.env.example','pyproject.toml','requirements.txt']:
            archive.write(ROOT/name, f'pet-aurora/{name}')
        for folder in ['petz','kit','evals','tests','scripts']:
            for path in sorted((ROOT/folder).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                    archive.write(path, 'pet-aurora/'+path.relative_to(ROOT).as_posix())
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        print(f'{target}: {len(archive.namelist())} arquivos, {target.stat().st_size} bytes')

if __name__ == '__main__': main()
