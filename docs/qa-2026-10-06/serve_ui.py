"""Isolated QA UI server. Only binds 127.0.0.1:8110; never uses dev.db."""
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'backend'))
os.environ['DATABASE_URL']='sqlite:///'+(OUT/'ui.db').as_posix()
os.environ['SMTP_HOST']=''
os.environ['FRONTEND_URL']='http://127.0.0.1:8110'
from app.main import app
from app.core.db import Base,engine,SessionLocal
from app.core import mail
from app.modules.auth.models import User
from sqlalchemy import select,func
from scripts.seed import seed
from fastapi.responses import FileResponse,JSONResponse
mail.send_mail=lambda *args:None
Base.metadata.create_all(engine)
with SessionLocal() as db:
    empty=not db.scalar(select(func.count()).select_from(User))
if empty: print(seed(100,7),flush=True)
DIST=(ROOT/'frontend/dist').resolve()
@app.get('/{path:path}',include_in_schema=False)
def spa(path:str):
    if path.startswith('api/'):
        return JSONResponse({'detail':'Not Found'},status_code=404)
    target=(DIST/path).resolve()
    if not target.is_relative_to(DIST):return JSONResponse({},status_code=404)
    return FileResponse(target if target.is_file() else DIST/'index.html')
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8110,log_level='warning')
