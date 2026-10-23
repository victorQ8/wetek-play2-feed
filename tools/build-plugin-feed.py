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
import shutil
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


def build(output, reuse=None):
    catalog = json.loads((ROOT / 'feed/catalog.json').read_text())
    locked = {s['name']: s for s in json.loads((ROOT / 'sources.lock.json').read_text())['sources']}
    output.mkdir(parents=True, exist_ok=False)
    feed = output / 'feed/py313-v1'
    feed.mkdir(parents=True)
    (output / 'sources').mkdir()
    index, provenance = [], []
    previous = json.loads((reuse / 'catalog.json').read_text()) if reuse else {'plugins': []}
    previous_provenance = json.loads((reuse / 'provenance.json').read_text()) if reuse else []
    for plugin in catalog['plugins']:
        source = ROOT / 'sources' / plugin['source']
        entry = locked[plugin['source']]
        subprocess.run(['python3', str(ROOT / 'tools/sources.py'), 'verify', plugin['source']], check=True)
        if plugin in previous['plugins']:
            metadata = next(p for p in previous_provenance if p['package'] == plugin['package'])
            patches = sorted((ROOT / 'patches/plugins' / plugin['module']).glob('*.patch'))
            if metadata['source'] != entry or metadata['patches'] != {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in patches}:
                raise ValueError('Changed published inputs require a package release bump: ' + plugin['package'])
            filename = f"{plugin['package']}_{metadata['version']}_{catalog['abi']}.ipk"
            old = reuse / 'feed/py313-v1' / filename
            assert hashlib.sha256(old.read_bytes()).hexdigest() == metadata['sha256']
            shutil.copyfile(old, feed / filename)
            stanzas = (reuse / 'feed/py313-v1/Packages').read_text().strip().split('\n\n')
            index.append(next(s for s in stanzas if s.startswith('Package: ' + plugin['package'] + '\n')) + '\n')
            archive = plugin['source'] + '-' + entry['commit'] + '.tar.gz'
            shutil.copyfile(reuse / 'sources' / archive, output / 'sources' / archive)
            old_patches = reuse / 'patches' / plugin['module']
            if old_patches.exists():
                shutil.copytree(old_patches, output / 'patches' / plugin['module'])
            provenance.append(metadata)
            continue
        module = plugin['module']
        assert re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', module)
        group = plugin.get('group', 'Extensions')
        assert group in ('Extensions', 'SystemPlugins', 'Python')
        prefix_base = 'usr/lib/python3/dist-packages/' if group == 'Python' else 'usr/lib/enigma2/python/Plugins/' + group + '/'
        package_prefix = 'wetek-python3-' if group == 'Python' else 'enigma2-plugin-' + group.lower() + '-'
        assert re.fullmatch(re.escape(package_prefix) + r'[a-z0-9][a-z0-9+-]*', plugin['package'])
        source_dir = source / plugin.get('source_dir', 'src/' + module)
        assert source_dir.resolve().is_relative_to(source.resolve())
        payload = {}
        for path in sorted(source_dir.rglob('*')):
            if path.is_dir():
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError(f'Unexpected source node: {path}')
            rel = path.relative_to(source_dir)
            if '__pycache__' in rel.parts or path.suffix in ('.pyc', '.pyo') or any(str(rel) == v or str(rel).startswith(v + '/') for v in plugin.get('exclude', [])):
                continue
            data = path.read_bytes()
            if data.startswith(b'\x7fELF') or path.suffix == '.so':
                raise ValueError(f'Native file in Python feed: {path}')
            if path.suffix == '.py':
                ast.parse(data, filename=str(path))
            payload[prefix_base + module + '/' + str(rel)] = data
        assert prefix_base + module + ('/__init__.py' if group == 'Python' else '/plugin.py') in payload
        payload[prefix_base + module + '/UPSTREAM-LICENSE.txt'] = (source / plugin.get('license_file', 'LICENSE.txt')).read_bytes()
        if plugin['license'] == 'GPL-2.0-only':
            payload[prefix_base + module + '/LICENSE-GPL-2.0.txt'] = (ROOT / 'feed/licenses/GPL-2.0.txt').read_bytes()
        patches = sorted((ROOT / 'patches/plugins' / module).glob('*.patch'))
        if patches:
            with tempfile.TemporaryDirectory(prefix='wetek-plugin-') as temp:
                exported = Path(temp)
                prefix = prefix_base + module + '/'
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
        payload[prefix_base + module + '/wetek-provenance.json'] = (json.dumps(metadata, indent=2) + '\n').encode()
        version = plugin['version'] + '+git' + entry['commit'][:12] + '-wetek' + str(plugin.get('release', 1))
        dependencies = ', '.join(['wetek-enigma2-api (= ' + catalog['api_version'] + ')'] + plugin.get('depends', []))
        control = (f"Package: {plugin['package']}\nVersion: {version}\nArchitecture: {catalog['abi']}\n"
                   f"Maintainer: WeTek Play 2 community port\nSection: enigma2\nPriority: optional\n"
                   f"Depends: {dependencies}\n"
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
    catalog['schema'] = 2
    catalog['packages_sha256'] = hashlib.sha256(packages).hexdigest()
    (feed / 'catalog-v2.json').write_text(json.dumps(catalog, indent=2) + '\n')
    (output / 'catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    (output / 'build-plugin-feed.py').write_bytes(Path(__file__).read_bytes())
    (output / 'README.md').write_text((ROOT / 'feed/README.md').read_text())
    shutil.copyfile(ROOT / 'feed/exclusions.json', output / 'exclusions.json')
    shutil.copytree(ROOT / 'feed/licenses', output / 'licenses')
    return provenance


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse', type=Path, help='Reuse identical published package versions byte for byte')
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.reuse), indent=2))
