"""Authenticated, bounded relay for files already listed in the publication database."""
from pathlib import PurePosixPath
import re
import threading
import urllib.parse

SLOTS=threading.BoundedSemaphore(2)
MIMES={'.pdf':'application/pdf','.zip':'application/zip','.rar':'application/vnd.rar',
       '.7z':'application/x-7z-compressed','.doc':'application/msword','.rtf':'application/rtf',
       '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
       '.xls':'application/vnd.ms-excel','.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}

class DownloadError(Exception):
    def __init__(self,status,message):super().__init__(message);self.status=status

def valid_file(raw,extension):
    if extension=='.pdf':return raw.startswith(b'%PDF')
    if extension in ('.zip','.docx','.xlsx'):return raw.startswith((b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08'))
    if extension=='.rar':return raw.startswith(b'Rar!\x1a\x07')
    if extension=='.7z':return raw.startswith(b'7z\xbc\xaf\x27\x1c')
    if extension in ('.doc','.xls'):return raw.startswith((b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1',b'{\\rtf'))
    if extension=='.rtf':return raw.lstrip().startswith(b'{\\rtf')
    return False

def document_file(url,connection,catalog,canonical,permitted,fetch):
    if not isinstance(url,str) or len(url)>5000:raise DownloadError(400,'Некорректная ссылка на документ')
    try:url=canonical(url)
    except ValueError as exc:raise DownloadError(400,'Некорректная ссылка на документ') from exc
    with connection() as con:
        row=con.execute('SELECT source_id FROM publications WHERE url=?',(url,)).fetchone()
    if not row:raise DownloadError(404,'Документ отсутствует в ленте')
    source=next((s for s in catalog() if s['id']==row['source_id']),None)
    if not source or not permitted(url,source):raise DownloadError(403,'Ссылка вне разрешённого источника')
    filename=PurePosixPath(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
    extension=PurePosixPath(filename).suffix.lower()
    if extension not in MIMES:raise DownloadError(415,'Это страница сайта, а не файл для скачивания')
    if not SLOTS.acquire(blocking=False):raise DownloadError(429,'Уже скачиваются два файла. Повторите через несколько секунд.')
    try:
        result=fetch(url,source)
        raw=result.get('raw',b'')
        if not raw or len(raw)>20*1024*1024:raise DownloadError(502,'Файл пустой или превышает ограничение 20 МБ')
        if not valid_file(raw,extension):raise DownloadError(502,'Источник вернул страницу или неподдерживаемый файл вместо документа. Откройте страницу источника в Яндексе.')
        filename=re.sub(r'[\x00-\x1f\x7f\\/]', '_', filename)[:180]
        return raw,filename,MIMES[extension]
    except DownloadError:raise
    except Exception as exc:
        raise DownloadError(502,'Не удалось получить файл от источника. Повторите позже или откройте его в Яндексе.') from exc
    finally:SLOTS.release()
