"""Fetch exact upstream sources needed alongside the public camera release."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import hashlib
import json
import os
import tarfile
import urllib.request

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'build/third_party_sources'
QT = 'https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/'
PYSIDE = 'https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/'
ITEMS = [
    ('qtbase', QT, 51220268, 'a951bd163c7b80fc6b8c88d7668fb56abf91c152373e13c10666763238131307'),
    ('qtimageformats', QT, 1848620, '0943132b5db8de6b6a7f1d162682173e8763c7ed94e80fd39113292845f67762'),
    ('qtsvg', QT, 2341876, 'e4ab39534ec97987b1b9b60ef7f4d3253d5912a69f8c713a01753174a4029331'),
    ('qttranslations', QT, 1745884, '85929c0c30d6f273f23bd879bb69803ea17b010ab73cab2f8abf95357f6f6bbb'),
    ('pyside-setup', PYSIDE, 18211772, '099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751'),
]
def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def fetch(item):
    name, prefix, size, expected = item
    assert len(expected) == 64
    filename = name + '-everywhere-src-6.12.0.tar.xz'
    target = OUT / filename
    url = prefix + filename
    if not (target.is_file() and target.stat().st_size == size and digest(target) == expected):
        temporary = target.with_suffix('.partial')
        request = urllib.request.Request(url, headers={'User-Agent': 'PriPara-source-package/1.1.1'})
        with urllib.request.urlopen(request, timeout=45) as response, temporary.open('wb') as stream:
            if not response.geturl().startswith('https://'):
                raise RuntimeError('An HTTPS source mirror is required')
            total = 0
            for block in iter(lambda: response.read(1024*1024), b''):
                total += len(block)
                if total > size:
                    raise RuntimeError('Unexpected source archive size')
                stream.write(block)
        assert temporary.stat().st_size == size and digest(temporary) == expected, filename
        os.replace(temporary, target)
    licenses = []
    with tarfile.open(target, 'r:xz') as archive:
        for entry in archive:
            parts = Path(entry.name).parts
            if not entry.isfile() or entry.size > 512*1024 or len(parts) < 2:
                continue
            leaf = parts[-1].upper()
            if parts[1].upper() == 'LICENSES' or (len(parts) == 2 and leaf.startswith(('LICENSE', 'COPYING'))):
                relative = Path(name).joinpath(*parts[1:])
                if '..' in relative.parts:
                    raise RuntimeError('Unsafe archive member')
                destination = OUT / 'license_texts' / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.extractfile(entry).read())
                licenses.append(relative.as_posix())
    print(json.dumps({'downloaded': filename, 'size': size, 'sha256': expected, 'licenseTexts': len(licenses)}), flush=True)
    return {'name': name, 'version': '6.12.0', 'filename': filename, 'url': url, 'size': size,
            'sha256': expected, 'hashSource': url + '.mirrorlist', 'licenseTexts': licenses}

OUT.mkdir(parents=True, exist_ok=True)
results = []
with ThreadPoolExecutor(max_workers=5) as executor:
    for result in as_completed([executor.submit(fetch, item) for item in ITEMS]):
        results.append(result.result())
results.sort(key=lambda r: r['name'])
manifest = {'schemaVersion': 1, 'version': '6.12.0', 'allUpstreamHashesVerified': True,
            'purpose': 'Exact Qt/PySide source archives for the matching binary release, not input game files.', 'files': results}
(OUT / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
(OUT / 'SHA256SUMS.txt').write_text(''.join(f"{r['sha256']}  {r['filename']}\n" for r in results), encoding='utf-8')
print(json.dumps({'passed': True, 'archives': len(results), 'totalBytes': sum(r['size'] for r in results)}), flush=True)
