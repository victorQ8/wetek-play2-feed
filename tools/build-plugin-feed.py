#!/usr/bin/env python3
"""Build a deterministic, Python-only opkg feed from pinned source exports."""
import argparse
import ast
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
PREFIX = 'usr/lib/enigma2/python/Plugins/Extensions/'


def tar_bytes(files):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    return gzip.compress(out.getvalue(), mtime=0)


def ar_bytes(files):
    out = b'!<arch>\n'
    for name, data in files.items():
        header = f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'
        assert len(header) == 60
        out += header.encode() + data + (b'\n' if len(data) % 2 else b'')
    return out


def build(output):
    catalog = json.loads((ROOT / 'feed/catalog.json').read_text())
    locked = {s['name']: s for s in json.loads((ROOT / 'sources.lock.json').read_text())['sources']}
    output.mkdir(parents=True, exist_ok=False)
    feed = output / 'feed/py313-v1'
    feed.mkdir(parents=True)
    (output / 'sources').mkdir()
    index, provenance = [], []
    for plugin in catalog['plugins']:
        source = ROOT / 'sources' / plugin['source']
        entry = locked[plugin['source']]
        subprocess.run(['python3', str(ROOT / 'tools/sources.py'), 'verify', plugin['source']], check=True)
        module = plugin['module']
        assert re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', module)
        assert plugin['package'].startswith('enigma2-plugin-extensions-')
        payload = {}
        for path in sorted((source / 'src' / module).rglob('*')):
            if path.is_dir():
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError(f'Unexpected source node: {path}')
            rel = path.relative_to(source / 'src' / module)
            if '__pycache__' in rel.parts or path.suffix in ('.pyc', '.pyo'):
                continue
            data = path.read_bytes()
            if data.startswith(b'\x7fELF') or path.suffix == '.so':
                raise ValueError(f'Native file in Python feed: {path}')
            if path.suffix == '.py':
                ast.parse(data, filename=str(path))
            payload[PREFIX + module + '/' + str(rel)] = data
        assert PREFIX + module + '/plugin.py' in payload
        payload[PREFIX + module + '/UPSTREAM-LICENSE.txt'] = (source / 'LICENSE.txt').read_bytes()
        patches = sorted((ROOT / 'patches/plugins' / module).glob('*.patch'))
        if patches:
            with tempfile.TemporaryDirectory(prefix='wetek-plugin-') as temp:
                exported = Path(temp)
                prefix = PREFIX + module + '/'
                for name, data in payload.items():
                    dest = exported / name.removeprefix(prefix)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                for patch in patches:
                    subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch)], cwd=exported, check=True)
                payload = {prefix + str(p.relative_to(exported)): p.read_bytes() for p in exported.rglob('*') if p.is_file()}
                for name, data in payload.items():
                    if name.endswith('.py'):
                        ast.parse(data, filename=name)
            patchdir = output / 'patches' / module
            patchdir.mkdir(parents=True)
            for patch in patches:
                (patchdir / patch.name).write_bytes(patch.read_bytes())
        metadata = {'source': entry, 'license': plugin['license'], 'packager_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'patches': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in patches}}
        payload[PREFIX + module + '/wetek-provenance.json'] = (json.dumps(metadata, indent=2) + '\n').encode()
        version = plugin['version'] + '+git' + entry['commit'][:12] + '-wetek1'
        control = (f"Package: {plugin['package']}\nVersion: {version}\nArchitecture: {catalog['abi']}\n"
                   f"Maintainer: WeTek Play 2 community port\nSection: enigma2\nPriority: optional\n"
                   f"Depends: wetek-enigma2-api (= {catalog['api_version']})\n"
                   f"Description: {plugin['description']}\nLicense: {plugin['license']}\n"
                   f"Homepage: {entry['url'].removesuffix('.git')}\n"
                   f"Installed-Size: {(sum(map(len, payload.values())) + 1023) // 1024}\n")
        ipk = ar_bytes({'debian-binary': b'2.0\n', 'control.tar.gz': tar_bytes({'control': control.encode()}), 'data.tar.gz': tar_bytes(payload)})
        name = f"{plugin['package']}_{version}_{catalog['abi']}.ipk"
        (feed / name).write_bytes(ipk)
        index.append(control + f'Filename: {name}\nSize: {len(ipk)}\nSHA256sum: {hashlib.sha256(ipk).hexdigest()}\n')
        archive = subprocess.check_output(['git', '-C', str(source), 'archive', '--format=tar', 'HEAD'])
        (output / 'sources' / (plugin['source'] + '-' + entry['commit'] + '.tar.gz')).write_bytes(gzip.compress(archive, mtime=0))
        provenance.append(metadata | {'package': plugin['package'], 'version': version, 'sha256': hashlib.sha256(ipk).hexdigest()})
    packages = ('\n'.join(index) + '\n').encode()
    (feed / 'Packages').write_bytes(packages)
    (feed / 'Packages.gz').write_bytes(gzip.compress(packages, mtime=0))
    (output / 'catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    (output / 'build-plugin-feed.py').write_bytes(Path(__file__).read_bytes())
    (output / 'README.md').write_text('''# WeTek Play 2 experimental Enigma2 plugin feed

Curated Python 3.13 plugins for the custom S905/GXBB runtime. This is not an
OpenATV release or a general OpenATV feed. Packages require wetek-enigma2-api
20261023. Do not add this feed to other receivers or firmware.

Browse `feed/py313-v1/Packages` for package descriptions. `provenance.json`
records exact upstream revisions; complete source exports are in `sources/`.
Each plugin carries its original license and authorship notices. AddStreamUrl
is GPLv3; AutoTimer, EPGSearch and EPGRefresh are CC BY-NC-SA 3.0 with the
upstream alternative license clause. This feed is distributed without charge
for noncommercial use; those three plugins must not be commercially distributed
outside their upstream license terms. Refer to each included LICENSE.txt.

Package installation and screen checks do not establish satellite reception,
IPTV-provider compatibility or successful recordings. See validation.json for
actual receiver test results. This feed contains no firmware, credentials or
receiver-specific settings.
''')
    return provenance


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
