"""Validate the complete release; explicit self-tests never start camera streams."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from assemble_release import ROOT, public_source_files

def sha(path):
    h=hashlib.sha256()
    with path.open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def blob_sha(blob):return hashlib.sha256(blob).hexdigest()

def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def inspect_zip(path):
    with zipfile.ZipFile(path)as archive:
        names=archive.namelist()
        assert len(names)==len(set(names)),path.name
        for name in names:
            parts=PurePosixPath(name)
            assert not parts.is_absolute()and'..'not in parts.parts and'\\'not in name and':'not in name,name
        assert archive.testzip()is None,path.name
    return names

def run_child(args,timeout=120):
    result=subprocess.run([str(a)for a in args],cwd=ROOT,capture_output=True,text=True,
                          encoding='utf-8',errors='replace',timeout=timeout,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise RuntimeError('Offline verification process failed: '+result.stdout[-3000:]+result.stderr[-3000:])
    return result

# Generic rules: no developer account, project path, or network is embedded.
PRIVATE_TEXT_PATTERN=re.compile(
    r'(?:[A-Z]:[\\/]Users[\\/][^\\/\s\"<>]+|/(?:home|Users)/[^/\s\"<>]+'
    r'|github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]{25,}'
    r'|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',re.I)
IPV4_CANDIDATE=re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])')

def contains_private_text(text):
    if PRIVATE_TEXT_PATTERN.search(text):return True
    for match in IPV4_CANDIDATE.finditer(text):
        octets=[int(part)for part in match.group().split('.')]
        if any(part>255 for part in octets):continue
        value=(octets[0]<<24)|(octets[1]<<16)|(octets[2]<<8)|octets[3]
        if any(value&mask==network for mask,network in (
                (0xff000000,0x0a000000),(0xfff00000,0xac100000),(0xffff0000,0xc0a80000))):return True
    return False

def verify(static_only=False):
    version=(ROOT/'VERSION').read_text('utf-8').strip()
    release=ROOT/'dist/release'/('v'+version)
    info=load(release/'release-manifest.json')
    assert info['version']==version and info['source_rebuilt_filters']and not info['pyvirtualcam_included']
    expected={f'PriParaImageCamera_Setup_{version}.exe',f'PriParaImageCamera_Complete_{version}.zip',
              f'PriParaImageCamera_Source_{version}.zip','PriParaImageCamera_QtSources_6.12.0.zip',
              'SHA256SUMS.txt','release-manifest.json'}
    assert {p.name for p in release.iterdir()if p.is_file()}==expected
    assets={e['name']:e for e in info['assets']}
    for name,entry in assets.items():
        path=release/name
        assert path.stat().st_size==entry['bytes']and sha(path)==entry['sha256'],name
        assert path.stat().st_size<2*1024**3
    lines=(release/'SHA256SUMS.txt').read_text('utf-8').splitlines()
    for line in lines:
        digest,name=line.split('  ',1)
        assert sha(release/name)==digest,name
    public=public_source_files()
    public_names={p.relative_to(ROOT).as_posix()for p in public}
    for path in public:
        relative=path.relative_to(ROOT).as_posix()
        assert not contains_private_text(path.read_text('utf-8-sig',errors='replace')),relative
        assert path.stat().st_size<100*1024*1024
        assert path.suffix.lower()not in('.exe','.dll','.pyc','.zip','.rar','.bmp','.png','.rgb','.yuy2')
    assert 'AssemblyVersion("'+version+'.0")'in(ROOT/'installer/Setup.cs').read_text('utf-8-sig')
    assert 'version="'+version+'.0"'in(ROOT/'installer/setup.manifest').read_text('utf-8-sig')
    source_zip=release/f'PriParaImageCamera_Source_{version}.zip'
    source_prefix='pripara-virtual-camera-'+version+'/'
    names=inspect_zip(source_zip)
    assert set(names)=={source_prefix+p for p in public_names}|{source_prefix+'SOURCE_MANIFEST.json'}
    with zipfile.ZipFile(source_zip)as archive:
        source_manifest=json.loads(archive.read(source_prefix+'SOURCE_MANIFEST.json'))
        assert {e['path']for e in source_manifest['files']}==public_names
        for entry in source_manifest['files']:
            original=ROOT/entry['path']
            assert sha(original)==entry['sha256']and original.stat().st_size==entry['bytes']
            assert archive.read(source_prefix+entry['path'])==original.read_bytes()
    github_zip=ROOT/'dist/pripara-virtual-camera-github-ready.zip'
    assert set(inspect_zip(github_zip))=={'pripara-virtual-camera/'+p for p in public_names}
    with zipfile.ZipFile(github_zip)as archive:
        for path in public:
            assert archive.read('pripara-virtual-camera/'+path.relative_to(ROOT).as_posix())==path.read_bytes()
    complete=release/f'PriParaImageCamera_Complete_{version}.zip'
    complete_names=inspect_zip(complete)
    with zipfile.ZipFile(complete)as archive:
        payload_manifest=json.loads(archive.read('manifest.json'))
        assert payload_manifest['version']==version
        assert {e['path']for e in payload_manifest['files']}==set(complete_names)-{'manifest.json'}
        for entry in payload_manifest['files']:
            value=archive.read(entry['path'])
            assert len(value)==entry['size']and blob_sha(value)==entry['sha256'],entry['path']
        for prefix in('UnityCaptureFilter','PriParaQRFilter'):
            for bits in(32,64):
                assert archive.read(f'Driver/{prefix}{bits}.dll')==(ROOT/f'build/native/{prefix}{bits}.dll').read_bytes()
        assert archive.read('App/_internal/native/PriParaFrameSender64.dll')==(ROOT/'build/native/PriParaFrameSender64.dll').read_bytes()
        assert 'App/source/ipc_files.py'in complete_names and'App/source/ticket_capture.py'in complete_names
        assert 'App/source/ticket_widgets.py'in complete_names
        assert any(p.endswith('/LGPL-3.0-only.txt')for p in complete_names)
        assert any(p.endswith('/GPL-3.0-only.txt')for p in complete_names)
        qt_files={PurePosixPath(p).name for p in complete_names if p.startswith('App/_internal/PySide6/')and p.endswith('.dll')and PurePosixPath(p).name.lower().startswith('qt6')}
        assert qt_files=={'Qt6Core.dll','Qt6Gui.dll','Qt6Network.dll','Qt6OpenGL.dll','Qt6Svg.dll','Qt6Widgets.dll'}
        assert not any('pyvirtualcam'in p.lower()or'virtualkeyboard'in p.lower()for p in complete_names)
        assert not any(any(part in('channels','ipc','TicketData')for part in PurePosixPath(p).parts)for p in complete_names)
    qt_source=release/'PriParaImageCamera_QtSources_6.12.0.zip'
    inspect_zip(qt_source)
    with zipfile.ZipFile(qt_source)as archive:
        source_info=json.loads(archive.read('source-manifest.json'))
        assert len(source_info['files'])==5 and source_info['allUpstreamHashesVerified']
        for entry in source_info['files']:
            raw=archive.read(entry['filename'])
            assert len(raw)==entry['size']and blob_sha(raw)==entry['sha256']
    proof={'passed':True,'version':version,'publicSourceFiles':len(public),
           'payloadFiles':len(complete_names),'majorAssets':info['assets'],'sourceZipBytes':github_zip.stat().st_size,
           'sourceZipSha256':sha(github_zip),'allAssetAndMemberHashesMatched':True,
           'QtCorrespondingSourceArchives':5,'pyvirtualcamBundled':False,'privateGameOrUserImagesIncluded':False,
           'staticOnly':static_only,'newRealCameraOrGameTest':False,'githubPublished':False}
    output=ROOT/'build/release-validation';output.mkdir(parents=True,exist_ok=True)
    if not static_only:
        # Reuse one extraction location only when its file contents already match
        # this exact installer payload; no recursive deletion is needed.
        extracted=output/('extracted-'+sha(complete)[:12])
        if not extracted.exists():
            run_child([release/f'PriParaImageCamera_Setup_{version}.exe','/extract',extracted])
        with zipfile.ZipFile(complete)as archive:
            for name in complete_names:
                assert (extracted/name).is_file()and(extracted/name).read_bytes()==archive.read(name),name
        frozen_report=output/'frozen-bundle.json'
        run_child([extracted/'App/PriParaImageCamera.exe','--offline-self-test',frozen_report])
        frozen=load(frozen_report)
        assert frozen['passed']and frozen['frozen']and not frozen['camera_opened']
        assert not frozen['QApplication_created']and not frozen['producer_started']
        assert frozen['sender_sha256']==sha(ROOT/'build/native/PriParaFrameSender64.dll')
        ps=Path(os.environ.get('WINDIR',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        run_child([ps,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
                   ROOT/'tests/test_installer_sandbox.ps1','-PayloadRoot',extracted,'-OutDir',output/'installer'],timeout=180)
        sandbox=load(output/'installer/installer-sandbox.json')
        assert sandbox.get('passed',sandbox.get('success',False)),sandbox
        proof.update(installerExtractedBytesMatched=True,frozenBundle=frozen,installerSandbox=sandbox)
        info.update(installer_sandbox_tested=True,frozen_bundle_tested=True,installer_resource_extraction_tested=True,
                    production_camera_registration_changed=False,other_PC_or_real_camera_game_tested=False)
        (release/'release-manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        sum_paths=[release/name for name in sorted(assets)]+[release/'release-manifest.json']
        (release/'SHA256SUMS.txt').write_text(''.join(sha(path)+'  '+path.name+'\n'for path in sum_paths),encoding='utf-8')
    report_name='validation-static.json'if static_only else'validation.json'
    (output/report_name).write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in proof.items()if k not in('majorAssets','frozenBundle','installerSandbox')},ensure_ascii=False,indent=2))
    return proof

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--static-only',action='store_true')
    verify(parser.parse_args().static_only)
