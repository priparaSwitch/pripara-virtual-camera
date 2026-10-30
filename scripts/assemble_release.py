"""Create self-contained release assets from this repository's clean builds."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[1]
SOURCE_TOP=('.github','app','native','installer','scripts','tests','docs','licenses')
SOURCE_ROOT=('README.md','THIRD_PARTY_NOTICES.md','VERSION','requirements.txt','requirements-build.txt','PriParaImageCamera.spec','.gitignore','.gitattributes')
SOURCE_EXT={'.py','.cpp','.h','.inl','.def','.cs','.manifest','.ps1','.md','.txt','.json','.yml','.yaml','.spec'}
def digest(path):
    h=hashlib.sha256()
    with path.open('rb')as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def public_source_files():
    paths=[]
    for name in SOURCE_ROOT:
        path=ROOT/name
        if not path.is_file():raise FileNotFoundError('Missing public source/document: '+name)
        paths.append(path)
    for name in SOURCE_TOP:
        for path in (ROOT/name).rglob('*'):
            if path.is_symlink():raise RuntimeError('Public sources must not contain symlinks')
            if not path.is_file()or(name!='licenses'and path.suffix.lower()not in SOURCE_EXT):continue
            rel=path.relative_to(ROOT)
            if any(part in ('__pycache__','ipc','channels','TicketData','data')for part in rel.parts):continue
            if name=='app'and 'native'in rel.parts:continue
            if name=='tests'and path.suffix.lower()=='.json':continue
            paths.append(path)
    return sorted(set(paths),key=lambda p:p.relative_to(ROOT).as_posix())
def reset_owned(path):
    resolved=path.resolve();allowed=(ROOT/'build/release-stage').resolve()
    if not resolved.is_relative_to(allowed)or resolved==allowed:raise RuntimeError('Unsafe stage reset')
    if path.exists():shutil.rmtree(path)
    path.mkdir(parents=True)
def zip_tree(source,dest,prefix=''):
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        for path in sorted(source.rglob('*')):
            if path.is_file():z.write(path,prefix+path.relative_to(source).as_posix())
def assemble(version):
    if version!=(ROOT/'VERSION').read_text('utf8').strip():raise ValueError('Version does not match source VERSION')
    native=json.loads((ROOT/'build/native/build-report.json').read_text('utf8'))
    app_report=json.loads((ROOT/'build/app-build-report.json').read_text('utf8'))
    offline=json.loads((ROOT/'build/offline-tests/validation.json').read_text('utf8'))
    if not native['passed']or not app_report['passed']or not offline['passed']:raise RuntimeError('Build/test reports failed')
    for entry in native['products']:
        if digest(ROOT/entry['path'])!=entry['sha256']:raise RuntimeError('Native build artifact changed')
    stage=ROOT/'build/release-stage'/('v'+version);reset_owned(stage)
    payload=stage/'payload';payload.mkdir();app=payload/'App';driver=payload/'Driver';setup=payload/'Setup'
    shutil.copytree(ROOT/'build/app-dist/PriParaImageCamera',app)
    if digest(app/'PriParaImageCamera.exe')!=app_report['application_exe_sha256']:raise RuntimeError('Frozen app changed')
    driver.mkdir();setup.mkdir()
    for prefix in ('UnityCaptureFilter','PriParaQRFilter'):
        for bits in (32,64):shutil.copy2(ROOT/'build/native'/f'{prefix}{bits}.dll',driver/f'{prefix}{bits}.dll')
    shutil.copytree(ROOT/'native',driver/'source')
    for name in ('Common.ps1','Install.ps1','Uninstall.ps1'):shutil.copy2(ROOT/'installer'/name,setup/name)
    shutil.copy2(ROOT/'installer/GameCameraSetup.ps1',app/'game_camera_setup.ps1')
    shutil.copytree(ROOT/'licenses',app/'licenses')
    shutil.copytree(ROOT/'docs',app/'docs')
    shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md',app/'THIRD_PARTY_NOTICES.md')
    shutil.copy2(ROOT/'docs/사용법.txt',payload/'설치안내.txt');shutil.copy2(ROOT/'docs/사용법.txt',app/'사용법.txt')
    (app/'source').mkdir()
    for path in (ROOT/'app').glob('*.py'):shutil.copy2(path,app/'source'/path.name)
    shutil.copy2(ROOT/'requirements.txt',app/'source/requirements.txt')
    public=public_source_files();source=payload/'Source';source.mkdir();source_manifest=[]
    for path in public:
        rel=path.relative_to(ROOT);target=source/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        source_manifest.append(dict(path=rel.as_posix(),bytes=path.stat().st_size,sha256=digest(path)))
    (source/'SOURCE_MANIFEST.json').write_text(json.dumps(dict(version=version,files=source_manifest),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    manifest=dict(product='PriParaImageCamera-1',version=version,vid='CAFE',upper_pid='0001',lower_pid='0002',files=[])
    for path in sorted(payload.rglob('*')):
        if path.is_file():manifest['files'].append(dict(path=path.relative_to(payload).as_posix(),sha256=digest(path),size=path.stat().st_size))
    (payload/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    release=ROOT/'dist/release'/('v'+version);release.mkdir(parents=True,exist_ok=True)
    complete=release/f'PriParaImageCamera_Complete_{version}.zip';zip_tree(payload,complete)
    source_zip=release/f'PriParaImageCamera_Source_{version}.zip';zip_tree(source,source_zip,prefix=f'pripara-virtual-camera-{version}/')
    github_zip=ROOT/'dist/pripara-virtual-camera-github-ready.zip'
    with zipfile.ZipFile(github_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        for path in public:z.write(path,'pripara-virtual-camera/'+path.relative_to(ROOT).as_posix())
    (ROOT/'dist/source-package-summary.json').write_text(json.dumps(dict(project='pripara-virtual-camera',
        sourcePackage=True,sourceFiles=[p.relative_to(ROOT).as_posix()for p in public],
        bytes=github_zip.stat().st_size,sha256=digest(github_zip),githubPublished=False),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    qt_cache=ROOT/'build/third_party_sources';qt_manifest=json.loads((qt_cache/'source-manifest.json').read_text('utf8'))
    qt_zip=release/'PriParaImageCamera_QtSources_6.12.0.zip'
    with zipfile.ZipFile(qt_zip,'w',zipfile.ZIP_STORED)as z:
        for entry in qt_manifest['files']:
            path=qt_cache/entry['filename']
            if path.stat().st_size!=entry['size']or digest(path)!=entry['sha256']:raise RuntimeError('Qt corresponding source integrity mismatch')
            z.write(path,path.name)
        for name in ('source-manifest.json','SHA256SUMS.txt'):z.write(qt_cache/name,name)
    executable=release/f'PriParaImageCamera_Setup_{version}.exe'
    csc=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    command=[str(csc),'/nologo','/target:winexe','/platform:x64','/optimize+','/codepage:65001','/utf8output',
             f'/out:{executable}',f'/win32manifest:{ROOT/"installer/setup.manifest"}',f'/resource:{complete},payload.zip',
             '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',str(ROOT/'installer/Setup.cs')]
    subprocess.run(command,cwd=ROOT,check=True)
    assets=[executable,complete,source_zip,qt_zip]
    if any(p.stat().st_size>=2*1024**3 for p in assets):raise RuntimeError('Release asset must be below2GiB')
    sums=''.join(f'{digest(p)}  {p.name}\n'for p in assets)
    (release/'SHA256SUMS.txt').write_text(sums,encoding='utf8')
    info=dict(version=version,application_runtime_version=app_report['version'],
              reused_binary_components=bool(app_report.get('reused_from_previous_package',False)),
              native_filters_rebuilt_for_this_package=not native.get('reused_from_previous_package',False),
              package_change='Remove machine-specific release-verification literals; runtime unchanged.',
              source_files=len(public),payload_files=len(manifest['files']),
              assets=[dict(name=p.name,bytes=p.stat().st_size,sha256=digest(p))for p in assets],
              Qt_DLLs=app_report['Qt_DLLs'],pyvirtualcam_included=False,source_rebuilt_filters=True,
              source_build_passed=True,offline_tests_passed=True,installer_sandbox_tested=False,
              other_PC_or_real_camera_game_tested=False,installed_driver_used_as_build_input=False,
              game_or_private_images_included=False,unsigned=True)
    (release/'release-manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (ROOT/'build/current-package.json').write_text(json.dumps(dict(version=version,payload=payload.relative_to(ROOT).as_posix(),setup=executable.relative_to(ROOT).as_posix(),release=release.relative_to(ROOT).as_posix()),indent=2)+'\n',encoding='utf8')
    print(json.dumps(info));return info
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--version',default=(ROOT/'VERSION').read_text().strip());a=p.parse_args();assemble(a.version)
