"""Bounded plain-text extraction. Files are never executed or unpacked to disk."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import zipfile
import xml.etree.ElementTree as ET

MAX_TEXT=60000
VERSION=2

def extract(raw):
    if len(raw)>20*1024*1024:return {'text':'','status':'oversize'}
    if raw.startswith(b'%PDF'):
        try:
            # Isolate complex PDF parsing; a malformed/decompression-heavy PDF
            # cannot consume the runner's memory or hang the collection worker.
            env={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','MEDPRAVO_OCR_ENABLED')}
            got=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--pdf-worker'],input=raw,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=40 if os.environ.get('MEDPRAVO_OCR_ENABLED')=='1' else 10,env=env)
            if got.returncode!=0:return {'text':'','status':'pdf_error'}
            return json.loads(got.stdout)
        except (subprocess.TimeoutExpired,ValueError,OSError):return {'text':'','status':'pdf_error'}
    if raw.startswith(b'PK'):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if len(archive.infolist())>2000:return {'text':'','status':'unsupported_archive'}
                info=archive.getinfo('word/document.xml')
                if info.file_size>2*1024*1024:return {'text':'','status':'oversize'}
                tree=ET.fromstring(archive.read(info))
                text=' '.join(n.text or '' for n in tree.iter() if n.tag.endswith('}t'))[:MAX_TEXT]
                return {'text':text,'status':'docx_text' if text.strip() else 'no_text'}
        except (KeyError,ValueError,zipfile.BadZipFile,ET.ParseError,RuntimeError):pass
    return {'text':'','status':'unsupported_file'}

def pdf_worker():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    except ImportError:pass
    from pypdf import PdfReader
    raw=sys.stdin.buffer.read(20*1024*1024+1)
    reader=PdfReader(io.BytesIO(raw))
    if reader.is_encrypted and not reader.decrypt(''):
        print(json.dumps({'text':'','status':'encrypted'}));return
    pieces=[];count=0
    for page in reader.pages[:30]:
        text=page.extract_text() or '';pieces.append(text);count+=len(text)
        if count>=MAX_TEXT:break
    text='\n'.join(pieces)[:MAX_TEXT]
    meaningful=sum(c.isalpha() for c in text)
    status='pdf_text' if meaningful>=30 else 'scan_needs_ocr'
    if meaningful<30 and os.environ.get('MEDPRAVO_OCR_ENABLED')=='1' and shutil.which('pdftoppm') and shutil.which('tesseract'):
        try:
            with tempfile.TemporaryDirectory(prefix='medpravo-ocr-') as folder:
                path=Path(folder);(path/'document.pdf').write_bytes(raw)
                subprocess.run(['pdftoppm','-f','1','-l','2','-scale-to','1800','-gray','-png',str(path/'document.pdf'),str(path/'page')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=12)
                pieces=[]
                for picture in sorted(path.glob('page-*.png'))[:2]:
                    if picture.stat().st_size>8*1024*1024:continue
                    got=subprocess.run(['tesseract',str(picture),'stdout','-l','rus+eng'],check=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10)
                    pieces.append(got.stdout.decode('utf-8',errors='replace'))
                text='\n'.join(pieces)[:MAX_TEXT]
                if sum(c.isalpha() for c in text)>=30:status='pdf_ocr';meaningful=30
        except (OSError,subprocess.SubprocessError):pass
    print(json.dumps({'text':text if meaningful>=30 else '', 'status':status}))

if __name__=='__main__' and sys.argv[1:]==['--pdf-worker']:pdf_worker()
