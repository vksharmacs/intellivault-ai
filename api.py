import os, shutil, time, uuid
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.config import settings
from app.database import get_db
from app.models import User, Document, Chunk
from app.schemas import Register, Login, QueryIn
from app.auth import hash_password,verify_password,create_token,current_user
from app.embeddings import embed
from app.reranker import rerank
from app.generator import answer, stream_answer
from app.tasks import ingest_pdf
from app.celery_app import celery
from app import query_cache
from app.prometheus_metrics import queries,total,cache_events,stream_latency
from app.security import rate_limit, security_headers
from app.malware import scan_file, MalwareDetected, MalwareScanError
from app.storage import upload as storage_upload, delete as storage_delete, object_key, StorageError
app=FastAPI(title="IntelliVault AI",version="1.0",docs_url="/docs" if settings.expose_docs else None,redoc_url=None,openapi_url="/openapi.json" if settings.expose_docs else None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=[h.strip() for h in settings.trusted_hosts.split(",") if h.strip()])
app.middleware("http")(security_headers)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(',')],allow_credentials=False,allow_methods=["GET","POST","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type","Accept"])
Path(settings.upload_dir).mkdir(parents=True,exist_ok=True)
@app.get('/health')
def health(): return {"status":"ok"}
@app.post('/auth/register')
def register(x:Register,request:Request,db:Session=Depends(get_db)):
    rate_limit(request,"auth",settings.auth_rate_limit_per_minute)
    email=x.email.lower()
    if db.scalar(select(User).where(User.email==email)): raise HTTPException(409,"Email already registered")
    u=User(email=email,full_name=x.full_name,password_hash=hash_password(x.password));db.add(u);db.commit();db.refresh(u)
    return {"access_token":create_token(u.id),"token_type":"bearer","user":{"id":u.id,"email":u.email,"full_name":u.full_name}}
@app.post('/auth/login')
def login(x:Login,request:Request,db:Session=Depends(get_db)):
    rate_limit(request,"auth",settings.auth_rate_limit_per_minute)
    u=db.scalar(select(User).where(User.email==x.email.lower()))
    if not u or not verify_password(x.password,u.password_hash): raise HTTPException(401,"Invalid credentials")
    return {"access_token":create_token(u.id),"token_type":"bearer","user":{"id":u.id,"email":u.email,"full_name":u.full_name}}
@app.get('/auth/me')
def me(u=Depends(current_user)): return {"id":u.id,"email":u.email,"full_name":u.full_name}
@app.get('/documents')
def docs(u=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(Document).where(Document.user_id==u.id).order_by(Document.created_at.desc())).all()
    return [{"id":d.id,"filename":d.filename,"status":d.status,"page_count":d.page_count,"chunk_count":d.chunk_count} for d in rows]
@app.post('/documents/upload',status_code=202)
def upload(request:Request,file:UploadFile=File(...),u=Depends(current_user),db:Session=Depends(get_db)):
    rate_limit(request,"upload",10)
    filename=os.path.basename(file.filename or "")
    if not filename.lower().endswith('.pdf'): raise HTTPException(415,"PDF extension required")
    document_uuid=uuid.uuid4().hex
    safe=f"{u.id}_{document_uuid}.pdf"; path=str(Path(settings.upload_dir)/safe)
    size=0; header=b""
    try:
        with open(path,'wb') as out:
            while True:
                block=file.file.read(1024*1024)
                if not block: break
                if not header: header=block[:5]
                size+=len(block)
                if size>settings.max_upload_bytes: raise HTTPException(413,"PDF exceeds upload size limit")
                out.write(block)
        if header!=b'%PDF-': raise HTTPException(415,"Invalid PDF signature")
    except Exception:
        try: os.remove(path)
        except OSError: pass
        raise
    try:
        scan_file(path)
    except MalwareDetected as exc:
        try: os.remove(path)
        except OSError: pass
        raise HTTPException(422,"Upload rejected by malware scanner") from exc
    except MalwareScanError as exc:
        try: os.remove(path)
        except OSError: pass
        raise HTTPException(503,"Upload scanning is temporarily unavailable") from exc
    key=object_key(u.id,document_uuid)
    try:
        storage_upload(path,key)
    except StorageError as exc:
        try: os.remove(path)
        except OSError: pass
        raise HTTPException(503,"Object storage is temporarily unavailable") from exc
    try: os.remove(path)
    except OSError: pass
    d=Document(user_id=u.id,filename=filename[:200],path=key,status='queued');db.add(d);db.commit();db.refresh(d)
    task=ingest_pdf.delay(d.id); return {"document":{"id":d.id,"filename":d.filename},"status":"queued","job_id":task.id}
@app.get('/jobs/{job_id}')
def job(job_id:str,u=Depends(current_user)):
    r=celery.AsyncResult(job_id); info=r.info if isinstance(r.info,dict) else {}; return {"job_id":job_id,"state":r.state,**info}
@app.delete('/documents/{document_id}')
def delete(document_id:int,u=Depends(current_user),db:Session=Depends(get_db)):
    d=db.scalar(select(Document).where(Document.id==document_id,Document.user_id==u.id))
    if not d: raise HTTPException(404,"Not found")
    try: storage_delete(d.path)
    except StorageError: raise HTTPException(503,"Object storage is temporarily unavailable")
    db.delete(d);db.commit();return {"deleted":True}
@app.post('/query')
def query(x:QueryIn,request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    rate_limit(request,'query')
    t=time.perf_counter(); version=db.scalar(select(func.max(Document.created_at)).where(Document.user_id==u.id))
    k=query_cache.key(u.id,x.language,str(version),x.question); hit=query_cache.get(k)
    if hit: cache_events.labels('answer','hit').inc(); hit['cache']='HIT'; return hit
    cache_events.labels('answer','miss').inc(); qv=embed(x.question)
    stmt=(select(Chunk,Document).join(Document,Chunk.document_id==Document.id).where(Document.user_id==u.id,Document.status=='ready').order_by(Chunk.embedding.cosine_distance(qv)).limit(x.top_k))
    rows=db.execute(stmt).all(); ranked=rerank(x.question,rows,5)
    sources=[{"document":d.filename,"document_id":d.id,"page":c.page,"text":c.text[:600]} for c,d in ranked]
    out={"answer":answer(x.question,ranked,x.language),"sources":sources,"language":x.language,"performance":{"total_ms":round((time.perf_counter()-t)*1000,2)}}
    query_cache.set_(k,out); queries.labels(x.language).inc(); total.observe(time.perf_counter()-t); out['cache']='MISS'; return out

@app.post('/query/stream')
def query_stream(x:QueryIn,request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    rate_limit(request,'query-stream')
    request_started=time.perf_counter()
    embedding_started=time.perf_counter(); qv=embed(x.question); embedding_ms=(time.perf_counter()-embedding_started)*1000
    retrieval_started=time.perf_counter()
    stmt=(select(Chunk,Document).join(Document,Chunk.document_id==Document.id).where(Document.user_id==u.id,Document.status=='ready').order_by(Chunk.embedding.cosine_distance(qv)).limit(x.top_k))
    rows=db.execute(stmt).all(); retrieval_ms=(time.perf_counter()-retrieval_started)*1000
    rerank_started=time.perf_counter(); ranked=rerank(x.question,rows,5); reranking_ms=(time.perf_counter()-rerank_started)*1000
    sources=[{"document":d.filename,"document_id":d.id,"page":c.page,"text":c.text[:600]} for c,d in ranked]
    def ndjson():
        yield __import__('json').dumps({"type":"sources","sources":sources},ensure_ascii=False)+"\n"
        collected=[]; generation_started=time.perf_counter(); first_token_at=None; token_events=0
        try:
            for token in stream_answer(x.question,ranked,x.language):
                now=time.perf_counter()
                if first_token_at is None:
                    first_token_at=now
                    ttft_ms=(first_token_at-request_started)*1000
                    model_ttft_ms=(first_token_at-generation_started)*1000
                    stream_latency.labels('ttft').observe(ttft_ms/1000)
                    stream_latency.labels('model_ttft').observe(model_ttft_ms/1000)
                    yield __import__('json').dumps({"type":"metrics","metrics":{"ttft_ms":round(ttft_ms,2),"model_ttft_ms":round(model_ttft_ms,2),"embedding_ms":round(embedding_ms,2),"retrieval_ms":round(retrieval_ms,2),"reranking_ms":round(reranking_ms,2)}},ensure_ascii=False)+"\n"
                token_events+=1; collected.append(token)
                yield __import__('json').dumps({"type":"token","text":token},ensure_ascii=False)+"\n"
            finished=time.perf_counter(); total_ms=(finished-request_started)*1000; generation_ms=(finished-generation_started)*1000
            stream_ms=(finished-first_token_at)*1000 if first_token_at else 0
            tokens_per_second=(token_events/(stream_ms/1000)) if stream_ms>0 else 0
            stream_latency.labels('total').observe(total_ms/1000); stream_latency.labels('generation').observe(generation_ms/1000)
            metrics={"ttft_ms":round((first_token_at-request_started)*1000,2) if first_token_at else None,"embedding_ms":round(embedding_ms,2),"retrieval_ms":round(retrieval_ms,2),"reranking_ms":round(reranking_ms,2),"generation_ms":round(generation_ms,2),"stream_ms":round(stream_ms,2),"total_ms":round(total_ms,2),"token_events":token_events,"token_events_per_second":round(tokens_per_second,2)}
            queries.labels(x.language).inc(); total.observe(total_ms/1000)
            version=db.scalar(select(func.max(Document.created_at)).where(Document.user_id==u.id)); k=query_cache.key(u.id,x.language,str(version),x.question)
            query_cache.set_(k,{"answer":"".join(collected),"sources":sources,"language":x.language,"performance":metrics})
            yield __import__('json').dumps({"type":"done","performance":metrics})+"\n"
        except Exception as exc:
            yield __import__('json').dumps({"type":"error","message":str(exc)})+"\n"
    return StreamingResponse(ndjson(),media_type="application/x-ndjson",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.get('/metrics')
def metrics():
    if not settings.expose_metrics: raise HTTPException(404,'Not found')
    return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
