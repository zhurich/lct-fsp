"""Additional deterministic races, API boundary matrix and bounded scaling probe."""
import audit as a
import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from datetime import timedelta
from sqlalchemy import select,func,event
from app.modules.assessment import router as ar
from app.modules.challenges.models import ChallengeAnswer
from app.modules.auth.models import User
from app.modules.matching.models import Need
from app.core.security import hash_password

def rec(name,status,**kw):
    row=dict(name=name,status=status,**kw); results.append(row)
    print(json.dumps(row,ensure_ascii=False),flush=True)
    (a.OUT/'extended-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

results=[]
with a.TestClient(a.app,raise_server_exceptions=False) as guest:
    c,cid=a.actor(); e,eid=a.actor('employer'); a.company(e)
    bads=[('/api/auth/register',{'email':'invalid','password':'short','role':'admin','consent':False}),('/api/candidate/assessment',{'specialization':'other','grade':'boss'}),('/api/candidate/profile',{'experience_years':-1}),('/api/candidate/profile',{'work_formats':['moon']}),('/api/candidate/profile',{'hidden_fields':['stack']}),('/api/candidate/fsp',{'fsp_id':'invalid'}),('/api/employer/needs',{'title':'x','specialization':'backend','grade':'middle','salary_from':20,'salary_to':10}),('/api/employer/vacancies',{'title':'x','description':'x','specialization':'backend','grade':'middle','salary_from':-1,'salary_to':10})]
    statuses=[]
    for path,body in bads:
        cl=e if '/employer/' in path else c
        method='PUT' if path.endswith('/profile') or path.endswith('/fsp') else 'POST'
        statuses.append([path,cl.request(method,path,json=body).status_code])
    rec('negative_validation_matrix','PASS' if all(x[1]==422 for x in statuses) else 'BUG',cases=statuses)
    for name,token in [('random','junk'),('expired',a.create_token(cid,'access',timedelta(seconds=-1))),('wrong_purpose',a.create_token(cid,'verify',timedelta(minutes=5)))]:
        with a.TestClient(a.app,raise_server_exceptions=False) as cl:
            cl.cookies.set('access_token',token);r=cl.get('/api/auth/me')
            rec('token_'+name,'PASS' if r.status_code==401 else 'BUG',http=r.status_code)
    # Same-account simultaneous starts: both precondition checks observe no active attempt.
    barrier=Barrier(2); original=ar._grade_locks
    def locks(*args,**kwargs):
        result=original(*args,**kwargs)
        if args[1]==cid and not hasattr(locks,'done'):barrier.wait(timeout=10)
        return result
    # Synchronize after first active-attempt lookup only, not state serialization.
    original_active=ar._active_attempt
    def active(db,uid,now):
        result=original_active(db,uid,now)
        if uid==cid and result is None:barrier.wait(timeout=10)
        return result
    a.profile(c)
    def start(_):
        with a.TestClient(a.app,raise_server_exceptions=False) as cl:
            cl.cookies.set('access_token',c.cookies.get('access_token'))
            r=cl.post('/api/candidate/assessment',json={'specialization':'backend','grade':'junior'})
            return r.status_code
    with patch.object(ar,'_active_attempt',side_effect=active):
        with ThreadPoolExecutor(max_workers=2) as ex:statuses=list(ex.map(start,range(2)))
    with a.SessionLocal() as db:
        ids=list(db.scalars(select(a.Assessment.id).where(a.Assessment.user_id==cid,a.Assessment.status==a.AttemptStatus.in_progress)))
    rec('parallel_assessment_start','BUG' if len(ids)>1 or 500 in statuses else 'PASS',http=statuses,active_ids=ids,scheduling='barrier after active-attempt read')
    # Both concurrent answers to same position succeed; resulting next questions differ and one is lost.
    c3,id3=a.actor(); a.profile(c3)
    st=c3.post('/api/candidate/assessment',json={'specialization':'qa','grade':'middle'}).json()
    aid=st['active']['id']; barrier2=Barrier(2)
    original_estimate=ar.adaptive.estimate
    def estimate(*args,**kwargs):
        result=original_estimate(*args,**kwargs);barrier2.wait(timeout=10);return result
    def answer(index):
        with a.TestClient(a.app,raise_server_exceptions=False) as cl:
            cl.cookies.set('access_token',c3.cookies.get('access_token'))
            r=cl.post(f'/api/candidate/assessment/{aid}/answer',json={'position':1,'answer':index})
            return {'status':r.status_code,'body':r.json() if r.status_code==200 else r.text}
    with patch.object(ar.adaptive,'estimate',side_effect=estimate):
        with ThreadPoolExecutor(max_workers=2) as ex:rs=list(ex.map(answer,range(2)))
    with a.SessionLocal() as db:
        stored=db.get(a.Assessment,aid).questions
    rec('parallel_assessment_answer','BUG' if all(x['status']==200 for x in rs) else 'PASS',http=[x['status'] for x in rs],different_next_questions=rs[0]['body']!=rs[1]['body'],stored_first_answer=stored[0].get('answer'),stored_question_count=len(stored),scheduling='barrier after both validate same position')
    # FSP mock edge cases and claimable identity: documented limitation, not real integration.
    c4,id4=a.actor()
    first=c4.put('/api/candidate/fsp',json={'fsp_id':'FSP-123456'})
    duplicate=c3.put('/api/candidate/fsp',json={'fsp_id':'FSP-123456'})
    unknown=c3.put('/api/candidate/fsp',json={'fsp_id':'FSP-000007'})
    unlinked=c4.delete('/api/candidate/fsp')
    rec('fsp_mock_lifecycle','PASS' if (first.status_code,duplicate.status_code,unknown.status_code,unlinked.status_code)==(200,409,404,200) else 'BUG',http=[first.status_code,duplicate.status_code,unknown.status_code,unlinked.status_code])
    # Close vacancy/challenge and deny fresh response.
    vdata=dict(title='test',description='test',specialization='backend',grade='middle',salary_from=1,salary_to=2,is_open=True)
    v=e.post('/api/employer/vacancies',json=vdata).json()
    update=e.put(f"/api/employer/vacancies/{v['id']}",json={**vdata,'is_open':False})
    r=c4.post(f"/api/candidate/vacancies/{v['id']}/apply",json={'message':''})
    rec('closed_vacancy_rejects_application','PASS' if r.status_code==404 else 'BUG',http=r.status_code)
    # Specialization test independence: fail one spec, attempt lower/higher in another.
    a.finish(c3,False)
    cross=c3.post('/api/candidate/assessment',json={'specialization':'backend','grade':'middle'})
    rec('cross_specialization_failure_lock','INFO',http=cross.status_code,detail=cross.json(),context='failed QA middle blocks backend middle too; clarify product decision')
    # Need matching honors hidden formats but salary is not part of Requirements.
    a.profile(c4,is_published=True,stack=['Python'],salary_expectation=500000)
    a.category(id4)
    nd=dict(title='Budget mismatch',specialization='backend',grade='middle',stack=['Python'],salary_from=50000,salary_to=100000)
    need=e.post('/api/employer/needs',json=nd).json()
    match=e.get(f"/api/employer/needs/{need['id']}/matches").json()
    selected=next(x for x in match['candidates'] if x['candidate_id']==id4)
    rec('salary_not_used_in_matching','INFO',salary_expectation=500000,budget_max=100000,score=selected['score'],context='expectation intentionally private; no overlap signal')
    # Bounded read benchmark at 100 / 1000 / 3000 candidates, no aggressive traffic.
    pw=hash_password('Synthetic123!')
    previous=0
    for target in [100,1000,3000]:
        with a.SessionLocal() as db:
            for i in range(previous,target):
                user=User(email=f'scale{i}@example.com',password_hash=pw,role=a.Role.candidate,email_verified=True,consent_at=a.utcnow())
                db.add(user); db.flush()
                db.add(a.CandidateProfile(user_id=user.id,is_published=True,stack=['Python'],specialization='backend'))
                db.add(a.CandidateCategory(user_id=user.id,specialization='backend',grade='middle',score=.7))
            db.commit()
        previous=target
        times=[]
        for _ in range(3):
            t=time.perf_counter();r=e.get('/api/employer/candidates');times.append(round((time.perf_counter()-t)*1000,1))
        rec('bank_scale_'+str(target),'INFO',http=r.status_code,total=len(r.json()),response_bytes=len(r.content),latency_ms=times,environment='in-process TestClient, SQLite, no network')
    # All other test setup gone with employer deletion, unaffected candidates remain.
    r=e.delete('/api/auth/me')
    with a.SessionLocal() as db: own=db.scalar(select(func.count()).select_from(Need).where(Need.employer_id==eid)); survivor=db.get(User,id4) is not None
    rec('employer_account_erasure','PASS' if r.status_code==204 and own==0 and survivor else 'BUG',http=r.status_code,needs_remaining=own,candidate_preserved=survivor)
