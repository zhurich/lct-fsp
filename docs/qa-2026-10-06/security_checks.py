"""Bounded security checks against isolated synthetic data; outgoing mail is stubbed."""
import audit as a
import json
from unittest.mock import patch
from io import BytesIO
from pypdf import PdfWriter
out=[]
def rec(name,status,**kw):out.append(dict(name=name,status=status,**kw))
with a.TestClient(a.app,raise_server_exceptions=False) as guest:
    c,cid=a.actor();e,eid=a.actor('employer');a.company(e)
    statuses=[guest.post('/api/auth/login',json={'email':'nonexistent@example.com','password':"' OR 1=1 --"}).status_code for _ in range(5)]
    rec('sql_injection_login','PASS' if set(statuses)=={401} else 'BUG',http=statuses)
    address=c.get('/api/auth/me').json()['email']
    statuses=[guest.post('/api/auth/login',json={'email':address,'password':'wrong-password'}).status_code for _ in range(30)]
    rec('login_throttle','LIMITATION' if set(statuses)=={401} else 'INFO',count=30,http=sorted(set(statuses)))
    forms=c.post('/api/candidate/profile',data={'full_name':'CSRF'})
    form_put=c.put('/api/candidate/profile',data={'full_name':'CSRF'})
    preflight=guest.options('/api/candidate/profile',headers={'Origin':'https://outside.example','Access-Control-Request-Method':'PUT','Access-Control-Request-Headers':'content-type'})
    rec('cross_origin_form_and_preflight','PASS' if forms.status_code==405 and form_put.status_code==422 and not preflight.headers.get('access-control-allow-origin') else 'BUG',form_post=forms.status_code,form_put=form_put.status_code,preflight=preflight.status_code,allow_origin=preflight.headers.get('access-control-allow-origin'))
    writer=PdfWriter();writer.add_blank_page(200,200);writer.encrypt('QA-only-password');f=BytesIO();writer.write(f)
    r=c.post('/api/candidate/profile/resume',files={'file':('encrypted.pdf',f.getvalue(),'application/pdf')})
    rec('encrypted_pdf','PASS' if r.status_code==422 else 'BUG',http=r.status_code)
    statuses=[]
    for value in ['NaN','Infinity','-Infinity']:
        r=c.put('/api/candidate/profile',content='{"experience_years":'+value+'}',headers={'content-type':'application/json'});statuses.append(r.status_code)
    rec('nonfinite_experience','PASS' if set(statuses)=={422} else 'BUG',http=statuses)
    r=guest.post('/api/auth/login',json={'email':address.upper(),'password':'AuditTest123!'})
    rec('email_case_normalization','PASS' if r.status_code==200 else 'BUG',http=r.status_code)
    headers=r.headers.get('set-cookie','')
    rec('cookie_flags','PASS' if 'HttpOnly' in headers and 'SameSite=lax' in headers else 'BUG',httponly='HttpOnly' in headers,samesite_lax='SameSite=lax' in headers,secure='Secure' in headers,context='secure false in local HTTP configuration')
    # The new user is not verified: regular authentication must be denied.
    guest.post('/api/auth/register',json=dict(email='unverified@example.com',password='AuditTest123!',role='candidate',consent=True))
    r=guest.post('/api/auth/login',json=dict(email='unverified@example.com',password='AuditTest123!'))
    rec('unverified_login','PASS' if r.status_code==403 else 'BUG',http=r.status_code)
(a.OUT/'security-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
