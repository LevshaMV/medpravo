"""Publication cutoff; discovery time and effective dates never establish recency."""
import datetime as dt
import re

SINCE='2026-10-01'

def date(value):
    if not isinstance(value,str):return None
    try:return dt.date.fromisoformat(value[:10]).isoformat()
    except ValueError:return None

def eligible(value):
    day=date(value)
    return bool(day and SINCE<=day<=dt.datetime.now(dt.timezone.utc).date().isoformat())

def prune(connection):
    """Remove old and undated records, including child rows, from current state."""
    with connection() as con:
        removed=[r['url'] for r in con.execute('SELECT url,published_at FROM publications') if not eligible(r['published_at'])]
        for url in removed:
            for table in ('publication_sources','publication_labels','publication_locations'):
                con.execute('DELETE FROM '+table+' WHERE url=?',(url,))
            con.execute('DELETE FROM publications WHERE url=?',(url,))
        # An explicitly dated old candidate needs no download; unknown candidates
        # may still acquire a trustworthy date from their individual source page.
        for row in con.execute('SELECT source_id,url,published_at FROM pending_documents').fetchall():
            day=date(row['published_at'])
            if day and day<SINCE:con.execute('DELETE FROM pending_documents WHERE source_id=? AND url=?',(row['source_id'],row['url']))
    return len(removed)
