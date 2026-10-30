"""Download and verify the pinned compiler; outputs stay under ignored .tools/."""
from pathlib import Path
import hashlib,json,os,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    info=json.loads((ROOT/'scripts/toolchain.json').read_text('utf8'))
    tools=ROOT/'.tools';tools.mkdir(exist_ok=True);archive=tools/info['archive']
    def good():return archive.is_file()and archive.stat().st_size==info['bytes']and hashlib.sha256(archive.read_bytes()).hexdigest()==info['sha256']
    if not good():
        temporary=archive.with_suffix('.partial')
        with urllib.request.urlopen(info['url'],timeout=60)as source,temporary.open('wb')as dest:
            for block in iter(lambda:source.read(1024*1024),b''):dest.write(block)
        if temporary.stat().st_size!=info['bytes']or hashlib.sha256(temporary.read_bytes()).hexdigest()!=info['sha256']:raise RuntimeError('Compiler archive integrity mismatch')
        os.replace(temporary,archive)
    with zipfile.ZipFile(archive)as z:
        for member in z.infolist():
            target=(tools/member.filename).resolve()
            if not target.is_relative_to(tools.resolve()):raise RuntimeError('Unsafe compiler archive path')
        z.extractall(tools)
    print('Verified compiler',info['version'])
if __name__=='__main__':main()
