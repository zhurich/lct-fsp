"""Reproducible QA probes. Synthetic isolated SQLite only; no production changes.
Run from repo root: backend/.venv/Scripts/python docs/qa-2026-10-06/audit.py
BUG means a reproduced issue, PASS a verified invariant, INFO an observed limitation.
"""
import io
import json
import logging
import os
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DATABASE_URL'] = 'sqlite:///' + (OUT / ('audit-' + uuid.uuid4().hex + '.db')).as_posix()
os.environ['SMTP_HOST'] = ''
from fastapi.testclient import TestClient
from sqlalchemy import select, func, event
from app.main import app
from app.core import mail
from app.core.db import SessionLocal, utcnow, Base, engine
from app.core.config import settings
from app.core.security import create_token
from app.modules.auth.models import User, Role
from app.modules.assessment.models import Assessment, CandidateCategory, AttemptStatus
from app.modules.candidates.models import CandidateProfile
from app.modules.invitations.models import Invitation
from app.modules.challenges.models import ChallengeAnswer
from app.modules.vacancies.models import Application
from app.modules.matching.ranking import CandidateData, Requirements, rank
from app.modules.candidates.resume import parse_resume
from app.modules.fsp.registry import registry
logging.disable(logging.CRITICAL)

RESULTS = []
M = []
mail.send_mail = lambda to, subject, body: M.append({'to': to, 'body': body})

def record(name, status, **details):
    row = dict(name=name, status=status, **details)
    RESULTS.append(row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
    (OUT / 'api-results.json').write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding='utf-8')

def actor(role='candidate', label=None):
    c = TestClient(app, raise_server_exceptions=False)
    email = (label or uuid.uuid4().hex) + '@example.com'
    r = c.post('/api/auth/register', json=dict(email=email, password='AuditTest123!', role=role, consent=True))
    assert r.status_code == 201, r.text
    token = re.search(r'token=(\S+)', M[-1]['body']).group(1)
    assert c.post('/api/auth/verify', json={'token': token}).status_code == 200
    r = c.post('/api/auth/login', json=dict(email=email, password='AuditTest123!'))
    assert r.status_code == 200, r.text
    return c, r.json()['id']

def profile(c, **changes):
    data = c.get('/api/candidate/profile').json()
    data.update(changes)
    r = c.put('/api/candidate/profile', json=data)
    assert r.status_code == 200, r.text
    return r.json()

def company(c):
    assert c.put('/api/employer/company', json={'name':'QA Company','contact_email':'qa@example.com'}).status_code == 200

def category(uid, grade='middle', age=0):
    with SessionLocal() as db:
        obj = db.get(CandidateCategory, uid) or CandidateCategory(user_id=uid)
        obj.specialization='backend'; obj.grade=grade; obj.score=.75
        obj.assigned_at=utcnow()-timedelta(days=age)
        db.add(obj); db.commit()

def finish(c, correct=True):
    state=c.get('/api/candidate/assessment').json()
    while state['active']:
        active=state['active']
        with SessionLocal() as db:
            answer=db.get(Assessment,active['id']).questions[-1]['correct']
        r=c.post(f"/api/candidate/assessment/{active['id']}/answer",json={'position':active['position'],'answer':answer if correct else None})
        assert r.status_code==200,r.text
        state=r.json()
    return state

def run():
    with TestClient(app, raise_server_exceptions=False) as guest:
        c,cid=actor(label='audit-candidate'); e,eid=actor('employer','audit-employer')
        c2,cid2=actor(); e2,eid2=actor('employer'); company(e); company(e2)
        record('registration_verification_login', 'PASS', candidate_id=cid, employer_id=eid)
        paths=['/candidate/profile','/candidate/assessment','/candidate/invitations','/candidate/vacancies','/candidate/applications','/candidate/challenges','/candidate/answers','/employer/company','/employer/candidates','/employer/needs','/employer/invitations','/employer/vacancies','/employer/challenges']
        statuses={p:guest.get('/api'+p).status_code for p in paths}
        roles={p:(e if p.startswith('/candidate') else c).get('/api'+p).status_code for p in paths}
        record('auth_and_role_matrix','PASS' if set(statuses.values())=={401} and set(roles.values())=={403} else 'BUG',anonymous=statuses,wrong_role=roles)
        r=c.post('/api/candidate/assessment',json={'specialization':'backend','grade':'junior','stack':['Python']})
        assert r.status_code==201,r.text
        aid=r.json()['active']['id']
        record('answer_key_not_exposed','PASS' if set(r.json()['active']['question'])=={'text','code','options'} else 'BUG',keys=list(r.json()['active']['question']))
        r=c2.post(f'/api/candidate/assessment/{aid}/answer',json={'position':1,'answer':0})
        record('assessment_ownership','PASS' if r.status_code==404 else 'BUG',http=r.status_code)
        r=c.post(f'/api/candidate/assessment/{aid}/answer',json={'position':1,'answer':999})
        record('invalid_answer_consumes_question','BUG' if r.status_code==200 else 'PASS',http=r.status_code,position=r.json().get('active',{}).get('position'))
        r=c.post(f'/api/candidate/assessment/{aid}/answer',json={'position':1,'answer':0})
        record('valid_first_answer','PASS' if r.status_code==200 else 'BUG',http=r.status_code)
        r=c.post(f'/api/candidate/assessment/{aid}/answer',json={'position':1,'answer':0})
        record('sequential_answer_replay','PASS' if r.status_code==409 else 'BUG',http=r.status_code)
        state=finish(c)
        record('assessment_full_completion','PASS' if state['category'] else 'BUG',category=state['category'],result=state['history'][0])
        locked=c.post('/api/candidate/assessment',json={'specialization':'backend','grade':'junior'})
        record('grade_cooldown','PASS' if locked.status_code==409 else 'BUG',http=locked.status_code)
        profile(c,full_name='Тестовый Кандидат',phone='+7 999 000 00 01',experience_years=7,hidden_fields=['experience'],is_published=True)
        cards=e.get('/api/employer/candidates').json()
        card=next(x for x in cards if x['candidate_id']==cid)
        record('bank_contact_and_hidden_field_protection','PASS' if card['experience_years'] is None and not {'phone','email','full_name','telegram'} & set(card) else 'BUG',experience=card['experience_years'])
        payload=dict(candidate_id=cid,title='Backend developer',message='QA offer',salary_from=100000,salary_to=200000,contact='qa@example.com')
        inv=e.post('/api/employer/invitations',json=payload)
        assert inv.status_code==201,inv.text
        iid=inv.json()['id']; before=inv.json()['contacts']
        forbidden=c2.post(f'/api/candidate/invitations/{iid}/accept').status_code
        accepted=c.post(f'/api/candidate/invitations/{iid}/accept').status_code
        contacts=e.get('/api/employer/invitations').json()[0]['contacts']
        twice=c.post(f'/api/candidate/invitations/{iid}/decline').status_code
        record('invitation_contact_handshake','PASS' if before is None and forbidden==404 and accepted==200 and contacts['phone']=='+7 999 000 00 01' and twice==409 else 'BUG',before=before,foreign=forbidden,accept=accepted,after=contacts,repeat=twice)
        need_data=dict(title='QA need',specialization='backend',grade='junior',stack=['Python'])
        need=e.post('/api/employer/needs',json=need_data).json(); nid=need['id']
        vacancy_data=dict(title='QA vacancy',description='A backend engineering vacancy',specialization='backend',grade='junior',salary_from=100000,salary_to=200000)
        vacancy=e.post('/api/employer/vacancies',json=vacancy_data).json(); vid=vacancy['id']
        application=c.post(f'/api/candidate/vacancies/{vid}/apply',json={'message':'QA application'})
        assert application.status_code==201,application.text
        apps=e.get(f'/api/employer/vacancies/{vid}/applications').json()
        record('hidden_experience_leaks_in_applications','BUG' if apps[0]['experience_years']==7 else 'PASS',hidden_fields=['experience'],bank_value=card['experience_years'],application_value=apps[0]['experience_years'])
        probes={'need_read':e2.get(f'/api/employer/needs/{nid}/matches').status_code,'need_write':e2.put(f'/api/employer/needs/{nid}',json=need_data).status_code,'need_delete':e2.delete(f'/api/employer/needs/{nid}').status_code,'applications':e2.get(f'/api/employer/vacancies/{vid}/applications').status_code,'application_accept':e2.post(f"/api/employer/applications/{application.json()['id']}/accept").status_code}
        record('employer_resource_ownership','PASS' if set(probes.values())=={404} else 'BUG',http=probes)
        profile(c,is_published=False)
        present=any(x['candidate_id']==cid for x in e.get('/api/employer/candidates').json())
        invite_hidden=e2.post('/api/employer/invitations',json=payload).status_code
        record('unpublished_candidate_not_searchable','PASS' if not present and invite_hidden==404 else 'BUG',present=present,invite=invite_hidden)
        profile(c,is_published=True)
        challenge_data=dict(title='QA mobile',text='Explain a safe mobile application architecture.',specialization='mobile')
        challenge=e.post('/api/employer/challenges',json=challenge_data).json(); chid=challenge['id']
        offered=any(x['id']==chid for x in c.get('/api/candidate/challenges').json())
        junk=c.post(f'/api/candidate/challenges/{chid}/answer',json={'text':' '*50})
        record('blank_cross_specialization_challenge_answer','BUG' if junk.status_code==201 else 'PASS',offered=offered,category='backend',challenge_spec='mobile',http=junk.status_code,answer=junk.json())
        answerid=junk.json().get('id')
        if answerid:
            rating=e2.put(f'/api/employer/answers/{answerid}/rating',json={'rating':5}).status_code
            record('challenge_rating_ownership','PASS' if rating==404 else 'BUG',http=rating)
        # Required strings containing only whitespace.
        statuses={
          'need':e.post('/api/employer/needs',json={**need_data,'title':' '}).status_code,
          'vacancy':e.post('/api/employer/vacancies',json={**vacancy_data,'title':' ','description':' '}).status_code,
          'challenge':e.post('/api/employer/challenges',json={**challenge_data,'title':' ','text':' '*20}).status_code,
          'invitation':e2.post('/api/employer/invitations',json={**payload,'title':' ','message':' ','contact':' '}).status_code,
        }
        record('whitespace_required_fields','BUG' if 201 in statuses.values() else 'PASS',http=statuses)
        # Oversized positive ints pass Pydantic but overflow SQLite integer binding.
        huge=10**30
        statuses={'profile':c.put('/api/candidate/profile',json={'salary_expectation':huge}).status_code,'need':e.post('/api/employer/needs',json={**need_data,'salary_from':huge}).status_code,'vacancy':e.post('/api/employer/vacancies',json={**vacancy_data,'salary_from':huge,'salary_to':huge}).status_code,'resource_id':e.get('/api/employer/needs/'+str(huge)+'/matches').status_code}
        record('integer_overflow_500','BUG' if 500 in statuses.values() else 'PASS',http=statuses)
        # Logout clears browser cookie but does not revoke the previously issued JWT.
        old=c2.cookies.get('access_token'); c2.post('/api/auth/logout')
        with TestClient(app,raise_server_exceptions=False) as replay:
            replay.cookies.set('access_token',old)
            status=replay.get('/api/auth/me').status_code
        record('logout_token_replay','BUG' if status==200 else 'PASS',http=status,ttl_min=settings.access_token_ttl_min)
        # Default launch configuration permits offline forging; scope explicitly local default.
        with TestClient(app,raise_server_exceptions=False) as forged:
            forged.cookies.set('access_token',create_token(eid,'access',timedelta(minutes=5)))
            status=forged.get('/api/auth/me').status_code
        record('default_secret_impersonation','BUG' if settings.secret_key=='dev-secret-change-me-in-production-please' and status==200 else 'INFO',default_secret_active=settings.secret_key=='dev-secret-change-me-in-production-please',http=status)
        # Invalid signed subject crashes decode_token instead of rejecting.
        import jwt
        bad=jwt.encode({'sub':'not-an-int','purpose':'access','exp':utcnow()+timedelta(minutes=5)},settings.secret_key,algorithm='HS256')
        with TestClient(app,raise_server_exceptions=False) as client:
            client.cookies.set('access_token',bad)
            status=client.get('/api/auth/me').status_code
        record('signed_invalid_subject_500','BUG' if status==500 else 'PASS',http=status,precondition='valid signature, not exploitable with random unsigned token')
        # Simulate SMTP failure after a committed user row.
        with patch('app.core.mail.send_mail',side_effect=ConnectionRefusedError('QA injected SMTP outage')):
            r=guest.post('/api/auth/register',json=dict(email='smtp-failure@example.com',password='AuditTest123!',role='candidate',consent=True))
        again=guest.post('/api/auth/register',json=dict(email='smtp-failure@example.com',password='AuditTest123!',role='candidate',consent=True))
        record('smtp_failure_partial_registration','BUG' if r.status_code==500 and again.status_code==409 else 'PASS',first=r.status_code,retry=again.status_code)
        # Bounded abuse probe, mail is fully stubbed.
        burst=[guest.post('/api/auth/resend-verification',json={'email':'smtp-failure@example.com'}).status_code for _ in range(30)]
        record('verification_mail_no_throttle','BUG' if all(x==200 for x in burst) else 'PASS',requests=len(burst),http=sorted(set(burst)))
        # Bad PDF, encrypted PDF, oversized file and valid Cyrillic profile.
        bad=c.post('/api/candidate/profile/resume',files={'file':('bad.pdf',b'%PDF-invalid','application/pdf')})
        big=c.post('/api/candidate/profile/resume',files={'file':('big.pdf',b'%PDF'+b'x'*(5*1024*1024),'application/pdf')})
        pdf=c.get('/api/candidate/profile/pdf')
        if pdf.status_code==200:(OUT/'candidate-profile.pdf').write_bytes(pdf.content)
        record('pdf_basic_inputs','PASS' if bad.status_code==422 and big.status_code==413 and pdf.status_code==200 else 'BUG',corrupt=bad.status_code,oversize=big.status_code,export=pdf.status_code,bytes=len(pdf.content))
        long_profile=c.get('/api/candidate/profile').json(); long_profile['stack']=['x'*20000]
        too_long=c.put('/api/candidate/profile',json=long_profile)
        record('unbounded_tag_length','PASS' if too_long.status_code==422 else 'BUG',accepted_chars=20000,http=too_long.status_code)
        profile(c,stack=['Python'])
        # Deterministic race: synchronize both requests immediately after duplicate SELECT.
        def race(path,body,select_fragment,owner):
            barrier=Barrier(2)
            def hook(conn,cursor,statement,parameters,context,executemany):
                if statement.lstrip().upper().startswith('SELECT') and select_fragment in statement:
                    barrier.wait(timeout=10)
            event.listen(engine,'after_cursor_execute',hook)
            token=owner.cookies.get('access_token')
            def request(_):
                with TestClient(app,raise_server_exceptions=False) as cl:
                    cl.cookies.set('access_token',token)
                    rr=cl.post(path,json=body)
                    return {'status':rr.status_code,'body':rr.json() if rr.headers.get('content-type','').startswith('application/json') else rr.text}
            try:
                with ThreadPoolExecutor(max_workers=2) as ex: return list(ex.map(request,range(2)))
            finally:event.remove(engine,'after_cursor_execute',hook)
        rc,rid=actor(); profile(rc,is_published=True); category(rid)
        responses=race('/api/employer/invitations',{**payload,'candidate_id':rid},'invitations.status !=',e)
        with SessionLocal() as db: count=db.scalar(select(func.count()).select_from(Invitation).where(Invitation.candidate_id==rid))
        record('concurrent_duplicate_invitations','BUG' if count>1 or any(x['status']==500 for x in responses) else 'PASS',count=count,http=[x['status'] for x in responses],scheduling='barrier after existing-invitation SELECT')
        responses=race(f'/api/candidate/vacancies/{vid}/apply',{'message':'QA parallel application'},'count(*) AS count_1',rc)
        with SessionLocal() as db: count=db.scalar(select(func.count()).select_from(Application).where(Application.candidate_id==rid))
        record('concurrent_duplicate_applications','BUG' if count>1 or any(x['status']==500 for x in responses) else 'PASS',count=count,http=[x['status'] for x in responses],scheduling='barrier after duplicate count SELECT')
        # Privacy is guaranteed only for structured fields; resume about is forwarded as-is.
        profile(c,about='Контакт: qa-private@example.com, телефон +7 999 123 45 67')
        visible=next(x for x in e2.get('/api/employer/candidates').json() if x['candidate_id']==cid)['about']
        record('free_text_contact_disclosure','BUG' if 'qa-private@example.com' in visible else 'PASS',about=visible,context='structured contacts remain protected; about has no warning/redaction')
        # Untested user: can answer unrelated task via direct API and gain freshness.
        nc,nid2=actor()
        rr=nc.post(f'/api/candidate/challenges/{chid}/answer',json={'text':'x'*50})
        record('challenge_without_profile_or_category','INFO',http=rr.status_code)
        # Candidate deletion removes dependent records; check ownership tables by metadata.
        deleted=c.delete('/api/auth/me').status_code
        with SessionLocal() as db:
            remaining={table.name:db.scalar(select(func.count()).select_from(table).where(col==cid)) for table in Base.metadata.sorted_tables for col in table.columns if any(fk.target_fullname=='users.id' for fk in col.foreign_keys)}
        record('account_erasure','PASS' if deleted==204 and all(v==0 for v in remaining.values()) else 'BUG',http=deleted,remaining=remaining)
        # Salary parsing and resume education are heuristics: return as quality observations.
        parsed=parse_resume('Иван Иванов\nJunior разработчик\nОбразование\nУниверситет 2018–2022\nОпыт работы отсутствует',2026)
        record('education_counted_as_experience','BUG' if parsed.experience_years else 'PASS',experience_years=parsed.experience_years)
        # Weighted score can overturn one missing skill despite the ranking module guarantee.
        skills=['Python','PostgreSQL','Redis','Docker','Kubernetes','FastAPI','Git','Linux','Kafka','SQL']
        req=Requirements(specialization='backend',grade='middle',stack=skills)
        strong=CandidateData('backend','middle',.99,utcnow(),skills[:-1],[],registry.fetch('FSP-123456') or [])
        weak=CandidateData('backend','middle',.5,utcnow()-timedelta(days=365),skills,[],[])
        scores=[rank(req,x,utcnow()).score for x in [strong,weak]]
        record('ranking_strength_overrides_skill_fit','BUG' if scores[0]>scores[1] else 'PASS',missing_one_skill=scores[0],all_skills=scores[1])
        record('summary','INFO',counts={s:sum(r['status']==s for r in RESULTS) for s in ['PASS','BUG','INFO']},database=os.environ['DATABASE_URL'])

if __name__=='__main__':run()
