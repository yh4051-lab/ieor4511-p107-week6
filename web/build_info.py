"""Identify the application source, browser assets and scenario configuration."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build_id(root=None):
    """Hash file contents, not timestamps or a potentially stale package manifest."""
    root = Path(root) if root is not None else ROOT
    paths = set((root / 'p107').glob('*.py'))
    paths.update((root / 'web').glob('*.py'))
    paths.update((root / 'configs').glob('*.json'))
    paths.update(p for p in (root / 'web' / 'dist').glob('*') if p.is_file())
    digest = hashlib.sha256(b'p107-application-build-v1\0')
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
