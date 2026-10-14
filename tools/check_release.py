"""Check the distributed archive, plus repeatability on the current platform."""
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

import build_release


def contents(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(not n.startswith('sqt-read/') for n in names):
            raise ValueError('Invalid archive paths or duplicate entries')
        return {n.removeprefix('sqt-read/'): archive.read(n) for n in names}


def main():
    folder = build_release.ROOT / 'dist'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    archive = folder / manifest['archive']
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    expected = build_release.payload()
    if contents(archive) != expected:
        raise ValueError('Distributed archive differs from skill source')
    if manifest['sha256'] != digest or (folder / 'SHA256SUMS').read_text(encoding='utf-8').strip() != digest + '  ' + archive.name:
        raise ValueError('Archive checksum mismatch')
    if manifest['files'] != {n: hashlib.sha256(b).hexdigest() for n, b in expected.items()}:
        raise ValueError('File manifest mismatch')
    with tempfile.TemporaryDirectory() as tmp:
        first = build_release.build(Path(tmp) / 'first')
        second = build_release.build(Path(tmp) / 'second')
        if Path(first['archive']).read_bytes() != Path(second['archive']).read_bytes():
            raise ValueError('Build is not repeatable on this platform')
        if contents(first['archive']) != expected:
            raise ValueError('Rebuilt archive has different payload')
    # ZIP container metadata may differ between operating systems; content may not.
    print(json.dumps({'passed': True, 'files': len(expected), 'sha256': digest}))


if __name__ == '__main__':
    main()
