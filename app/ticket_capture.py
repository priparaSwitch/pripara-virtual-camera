"""Durable capture of completed BMP writes; source files are read-only."""
import hashlib,io,json,os,sqlite3,time,uuid
from datetime import datetime,timedelta
from pathlib import Path
from PIL import Image,UnidentifiedImageError
from ipc_files import read_bytes

DEFAULT_INPUT=Path(r'C:\prineohk\game')
DEFAULT_OUTPUT=Path(r'C:\prineohk\TicketData\MyTicket')
SPLIT_Y=508

def signature(stat):
    return json.dumps([stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns])

def png_bytes(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()

def publish_new(path,data):
    """Atomic on NTFS, and never overwrite an existing ticket."""
    if path.exists():
        if read_bytes(path)==data:return
        raise FileExistsError('기존 티켓 파일을 덮어쓰지 않습니다: '+path.name)
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_bytes(data)
        if os.name=='nt':os.rename(temporary,path)  # Windows rename never replaces.
        else:os.link(temporary,path);temporary.unlink()
    except FileExistsError:
        if read_bytes(path)!=data:raise
    finally:
        temporary.unlink(missing_ok=True)

def split_ticket(image):
    rotated=image.convert('RGB').transpose(Image.Transpose.ROTATE_90)
    if rotated.height<=SPLIT_Y:
        raise ValueError(f'회전한 이미지 높이가 {SPLIT_Y}픽셀보다 작거나 같습니다: {rotated.width}×{rotated.height}')
    return rotated,rotated.crop((0,0,rotated.width,SPLIT_Y)),rotated.crop((0,SPLIT_Y,rotated.width,rotated.height))

class TicketCapture:
    def __init__(self,input_dir=DEFAULT_INPUT,output_dir=DEFAULT_OUTPUT,settle=.75):
        self.input_dir=Path(input_dir);self.output_dir=Path(output_dir);self.settle=settle
        self.output_dir.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.output_dir/'.ticket_capture.sqlite3',timeout=5)
        self.db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS sources (path TEXT PRIMARY KEY,signature TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS captures (id TEXT PRIMARY KEY,path TEXT,stamp TEXT UNIQUE,state TEXT,details TEXT)')
        self.pending={};self.errors={};self.saved_count=0;self.last_error=None
        if not self.db.execute("SELECT value FROM meta WHERE key='initialized'").fetchone():
            # First launch watches future output, rather than importing old BMPs.
            for path,stat in self._scan():
                self.db.execute('INSERT OR REPLACE INTO sources VALUES (?,?)',(self._key(path),signature(stat)))
            self.db.execute("INSERT INTO meta VALUES ('initialized','1')");self.db.commit()
        self.known=dict(self.db.execute('SELECT path,signature FROM sources'))

    @staticmethod
    def _key(path):return str(path.resolve()).casefold()

    def _scan(self):
        if not self.input_dir.is_dir():return []
        result=[]
        for path in self.input_dir.iterdir():
            try:
                if path.suffix.lower()=='.bmp' and path.is_file():result.append((path,path.stat()))
            except OSError:continue
        return result

    def _mark_seen(self,path,sig):
        key=self._key(path);self.known[key]=sig
        self.db.execute('INSERT OR REPLACE INTO sources VALUES (?,?)',(key,sig));self.db.commit()
        self.pending.pop(key,None);self.errors.pop(key,None)

    def import_ready(self,path,stat):
        sig=signature(stat);blob=read_bytes(path)
        if len(blob)<14 or blob[:2]!=b'BM':raise ValueError('BMP 쓰기 완료 대기 중')
        declared=int.from_bytes(blob[2:6],'little')
        if declared and len(blob)<declared:raise ValueError('BMP 쓰기 완료 대기 중')
        with Image.open(io.BytesIO(blob)) as image:
            image.load();images=split_ticket(image)
        if signature(path.stat())!=sig:raise OSError('BMP 파일이 아직 갱신 중입니다.')
        source_hash=hashlib.sha256(blob).hexdigest()
        identity=hashlib.sha256((self._key(path)+'\0'+sig+'\0'+source_hash).encode()).hexdigest()
        job=self.db.execute('SELECT stamp,state,details FROM captures WHERE id=?',(identity,)).fetchone()
        if job:
            stamp=job[0]
        else:
            # New copies use creation time; overwrites use their later write time.
            moment=datetime.fromtimestamp(max(stat.st_ctime,stat.st_mtime))
            with self.db:
                while True:
                    stamp=moment.strftime('%Y-%m-%d_%H%M%S')
                    occupied=self.db.execute('SELECT 1 FROM captures WHERE stamp=?',(stamp,)).fetchone()
                    if not occupied and not any((self.output_dir/f'myticket_{stamp}{suffix}.png').exists() for suffix in ('','_tomo','_my')):break
                    moment+=timedelta(seconds=1)
                details={'source':str(path),'source_sha256':source_hash,'source_signature':sig,'size':list(images[0].size),'split_y':SPLIT_Y}
                self.db.execute('INSERT INTO captures VALUES (?,?,?,?,?)',(identity,self._key(path),stamp,'pending',json.dumps(details)))
        files=[self.output_dir/f'myticket_{stamp}{suffix}.png' for suffix in ('','_tomo','_my')]
        for image,destination in zip(images,files):publish_new(destination,png_bytes(image))
        with self.db:self.db.execute("UPDATE captures SET state='complete' WHERE id=?",(identity,))
        self._mark_seen(path,sig);self.saved_count+=1;self.last_error=None
        return {'source':str(path),'full':str(files[0]),'tomo':str(files[1]),'my':str(files[2]),'stamp':stamp,'size':list(images[0].size),'split_y':SPLIT_Y}

    def poll(self,now=None,stop_requested=lambda:False):
        now=time.monotonic() if now is None else now
        scanned=self._scan();found={self._key(path) for path,_ in scanned};events=[]
        for path,stat in scanned:
            if stop_requested():break
            key=self._key(path);sig=signature(stat)
            if self.known.get(key)==sig:continue
            pending=self.pending.get(key)
            if not pending or pending['sig']!=sig:
                self.pending[key]={'sig':sig,'stable_since':now,'next_try':now};continue
            if now-pending['stable_since']<self.settle or now<pending['next_try']:continue
            try:
                event=self.import_ready(path,stat);events.append(event)
            except (OSError,ValueError,UnidentifiedImageError,sqlite3.Error) as error:
                text=str(error);self.last_error=path.name+': '+text
                self.errors[key]=self.last_error;pending['next_try']=now+1
            if len(events)>=4:break
        for key in list(self.pending):
            if key not in found:self.pending.pop(key,None)
        return events

    def close(self):self.db.close()
