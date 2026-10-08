"""Docker-free IntelliVault AI development server.
Runs with SQLite + local files + deterministic semantic retrieval + simulated streaming LLM.
Production modules remain unchanged.
"""
import hashlib, json, math, re, sqlite3, time, uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, HTTPException, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'dev_data'; UPLOADS=DATA/'uploads'; DB=DATA/'intellivault-dev.db'
UPLOADS.mkdir(parents=True,exist_ok=True)
SECRET='intellivault-docker-free-development-only'
MAX_UPLOAD_BYTES=25*1024*1024
ph=PasswordHasher()
app=FastAPI(title='IntelliVault AI - Docker-free Development',version='1.0.0-dev')
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5173','http://localhost:5173'],allow_methods=['*'],allow_headers=['*'])

class AuthIn(BaseModel): email:EmailStr; password:str; full_name:str|None=None
class QueryIn(BaseModel): question:str; language:str='en'; top_k:int=8

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
    with conn() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,full_name TEXT,password_hash TEXT);CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY,user_id INTEGER,filename TEXT,path TEXT,status TEXT,page_count INTEGER DEFAULT 0,chunk_count INTEGER DEFAULT 0,created_at TEXT);CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY,document_id INTEGER,page INTEGER,text TEXT);''')
init()

def token(uid): return jwt.encode({'sub':str(uid),'exp':datetime.now(timezone.utc)+timedelta(hours=8)},SECRET,algorithm='HS256')
def user_from(auth):
    if not auth or not auth.startswith('Bearer '): raise HTTPException(401,'Authentication required')
    try: uid=int(jwt.decode(auth[7:],SECRET,algorithms=['HS256'])['sub'])
    except Exception: raise HTTPException(401,'Invalid token')
    with conn() as c: u=c.execute('select * from users where id=?',(uid,)).fetchone()
    if not u: raise HTTPException(401,'Unknown user')
    return u

def words(s): return re.findall(r'[\w\u0900-\u097f]+',s.lower())
def score(q,t):
    a,b=Counter(words(q)),Counter(words(t)); dot=sum(a[k]*b[k] for k in a); na=math.sqrt(sum(v*v for v in a.values())); nb=math.sqrt(sum(v*v for v in b.values())); return dot/(na*nb) if na and nb else 0.0

def chunk(text,n=170,overlap=25):
    w=text.split(); step=n-overlap; return [' '.join(w[i:i+n]) for i in range(0,len(w),step) if w[i:i+n]]

@app.get('/health')
def health(): return {'status':'ok','mode':'docker-free','database':'sqlite','storage':'local','llm':'simulated-streaming'}
@app.post('/auth/register')
def register(x:AuthIn):
    if not x.full_name: raise HTTPException(422,'full_name required')
    with conn() as c:
        try:
            cur=c.execute('insert into users(email,full_name,password_hash) values(?,?,?)',(x.email.lower(),x.full_name,ph.hash(x.password))); uid=cur.lastrowid
        except sqlite3.IntegrityError: raise HTTPException(409,'Email already registered')
    return {'access_token':token(uid),'token_type':'bearer','user':{'id':uid,'email':x.email,'full_name':x.full_name}}
@app.post('/auth/login')
def login(x:AuthIn):
    with conn() as c: u=c.execute('select * from users where email=?',(x.email.lower(),)).fetchone()
    try: ok=bool(u) and ph.verify(u['password_hash'],x.password)
    except VerifyMismatchError: ok=False
    if not ok: raise HTTPException(401,'Invalid credentials')
    return {'access_token':token(u['id']),'token_type':'bearer','user':{'id':u['id'],'email':u['email'],'full_name':u['full_name']}}
@app.get('/auth/me')
def me(authorization:str|None=Header(None)):
    u=user_from(authorization); return {'id':u['id'],'email':u['email'],'full_name':u['full_name']}
@app.get('/documents')
def documents(authorization:str|None=Header(None)):
    u=user_from(authorization)
    with conn() as c: rows=c.execute('select id,filename,status,page_count,chunk_count from documents where user_id=? order by id desc',(u['id'],)).fetchall()
    return [dict(x) for x in rows]
@app.post('/documents/upload',status_code=202)
async def upload(file:UploadFile=File(...),authorization:str|None=Header(None)):
    u=user_from(authorization); name=Path(file.filename or '').name
    if not name.lower().endswith('.pdf'): raise HTTPException(415,'PDF only')
    raw=await file.read(MAX_UPLOAD_BYTES+1)
    if len(raw)>MAX_UPLOAD_BYTES: raise HTTPException(413,'PDF too large')
    if not raw.startswith(b'%PDF-'): raise HTTPException(415,'Invalid PDF signature')
    path=UPLOADS/f'{u["id"]}_{uuid.uuid4().hex}.pdf'; path.write_bytes(raw)
    try: reader=PdfReader(str(path))
    except Exception: path.unlink(missing_ok=True); raise HTTPException(422,'Unreadable PDF')
    pages=[]
    for pn,p in enumerate(reader.pages,1):
        for txt in chunk(p.extract_text() or ''): pages.append((pn,txt))
    with conn() as c:
        cur=c.execute('insert into documents(user_id,filename,path,status,page_count,chunk_count,created_at) values(?,?,?,?,?,?,?)',(u['id'],name,str(path),'ready',len(reader.pages),len(pages),datetime.now(timezone.utc).isoformat())); did=cur.lastrowid
        c.executemany('insert into chunks(document_id,page,text) values(?,?,?)',[(did,p,t) for p,t in pages])
    jid='dev-'+uuid.uuid4().hex
    return {'document':{'id':did,'filename':name},'status':'ready','job_id':jid}
@app.get('/jobs/{job_id}')
def job(job_id:str,authorization:str|None=Header(None)):
    user_from(authorization); return {'job_id':job_id,'state':'SUCCESS','percent':100,'stage':'Ready'}
@app.delete('/documents/{document_id}')
def delete(document_id:int,authorization:str|None=Header(None)):
    u=user_from(authorization)
    with conn() as c:
        d=c.execute('select * from documents where id=? and user_id=?',(document_id,u['id'])).fetchone()
        if not d: raise HTTPException(404,'Not found')
        Path(d['path']).unlink(missing_ok=True); c.execute('delete from chunks where document_id=?',(document_id,)); c.execute('delete from documents where id=?',(document_id,))
    return {'deleted':True}

def retrieve(uid,q,n):
    with conn() as c: rows=c.execute('select c.*,d.filename from chunks c join documents d on d.id=c.document_id where d.user_id=?',(uid,)).fetchall()
    return sorted(rows,key=lambda r:score(q,r['text']),reverse=True)[:n]
def synthesized(q,rows,lang):
    if not rows: return 'दस्तावेज़ों में पर्याप्त जानकारी नहीं मिली।' if lang=='hi' else 'I could not find enough information in your documents.'
    lead='आपके दस्तावेज़ों के आधार पर' if lang=='hi' else 'Based on your documents'
    evidence=' '.join(r['text'] for r in rows[:3])[:1800]
    return f'{lead}: {evidence} [Source 1]'
@app.post('/query/stream')
def query_stream(x:QueryIn,authorization:str|None=Header(None)):
    u=user_from(authorization); started=time.perf_counter(); rs=retrieve(u['id'],x.question,x.top_k); ans=synthesized(x.question,rs,x.language)
    sources=[{'document':r['filename'],'document_id':r['document_id'],'page':r['page'],'text':r['text'][:600]} for r in rs[:5]]
    def gen():
        yield json.dumps({'type':'sources','sources':sources},ensure_ascii=False)+'\n'; first=time.perf_counter()
        yield json.dumps({'type':'metrics','metrics':{'ttft_ms':round((first-started)*1000,2),'retrieval_ms':round((first-started)*1000,2),'reranking_ms':0.0}},ensure_ascii=False)+'\n'
        parts=re.findall(r'\S+\s*',ans)
        for part in parts:
            yield json.dumps({'type':'token','text':part},ensure_ascii=False)+'\n'; time.sleep(.025)
        done=time.perf_counter(); yield json.dumps({'type':'done','performance':{'ttft_ms':round((first-started)*1000,2),'retrieval_ms':round((first-started)*1000,2),'reranking_ms':0.0,'generation_ms':round((done-first)*1000,2),'total_ms':round((done-started)*1000,2),'token_events_per_second':round(len(parts)/(done-first),2)}},ensure_ascii=False)+'\n'
    return StreamingResponse(gen(),media_type='application/x-ndjson')
@app.post('/query')
def query(x:QueryIn,authorization:str|None=Header(None)):
    u=user_from(authorization); rs=retrieve(u['id'],x.question,x.top_k); return {'answer':synthesized(x.question,rs,x.language),'sources':[{'document':r['filename'],'page':r['page'],'text':r['text'][:600]} for r in rs[:5]],'cache':'DEV'}
