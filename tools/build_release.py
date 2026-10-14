"""Build a deterministic, self-contained skill archive from an explicit allowlist."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.5.1'


def payload():
    files = [ROOT / 'SKILL.md', ROOT / 'requirements.txt']
    for folder, suffix in [('agents', '.yaml'), ('references', '.md'), ('scripts', '.py')]:
        files.extend(sorted((ROOT / folder).glob('*' + suffix)))
    if len(files) != 11:
        raise ValueError('Unexpected skill payload; review the allowlist before publishing')
    return {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in files}


def main():
    data = payload()
    target = ROOT / 'dist'
    target.mkdir(exist_ok=True)
    package = target / ('sqt-read-v' + VERSION + '.zip')
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(data.items()):
            info = zipfile.ZipInfo('sqt-read/' + name, date_time=(2026, 10, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compresslevel=9)
    with zipfile.ZipFile(package) as archive:
        actual = {n.removeprefix('sqt-read/'): archive.read(n) for n in archive.namelist()}
    if actual != data:
        raise ValueError('Archive contents differ from source')
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    manifest = {
        'name': 'sqt-read', 'version': VERSION, 'channel': 'stable',
        'baseline': 'sqt-read-lab 0.5.1', 'archive': package.name,
        'sha256': checksum,
        'files': {n: hashlib.sha256(b).hexdigest() for n, b in sorted(data.items())},
    }
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (target / 'SHA256SUMS').write_text(checksum + '  ' + package.name + '\n', encoding='utf-8')
    print(json.dumps({'archive': str(package), 'files': len(data), 'sha256': checksum}))


if __name__ == '__main__':
    main()
