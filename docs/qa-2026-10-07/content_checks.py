"""Content quality / construct validity probes independent from production data."""
import sys,json,random,ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'backend'))
from app.modules.assessment import bank,adaptive
from app.modules.reference.data import GRADES
from app.modules.matching.parser import parse_need
from dataclasses import asdict
result={}
syntax=[];runtime=[]
for seed in range(60):
    q=bank.ITEMS['common.complexity.3'].generate(random.Random(seed))
    try:
        ast.parse(q.code)
        scope={};exec(q.code,scope)
        name=next(k for k,v in scope.items() if callable(v) and k!='__builtins__')
        scope[name](4)
    except Exception as ex:
        runtime.append({'seed':seed,'error':type(ex).__name__+': '+str(ex),'code':q.code,'answer':q.options[q.correct]})
result['invalid_complexity_examples']={'failed':len(runtime),'sample_size':60,'examples':runtime[:3]}
def simulate(strategy,grade,seed):
    rng=random.Random(seed);theta=adaptive.start_theta(grade);used=set();responses=[];right=0
    for i in range(adaptive.TEST_LENGTH):
        pool=[x for x in bank.pool('backend',adaptive.is_specialized(i)) if x.id not in used]
        item=adaptive.pick_item(pool,theta,{},(),rng);used.add(item.id)
        q=item.generate(rng)
        if strategy=='longest':correct=max(range(4),key=lambda k:len(q.options[k]))==q.correct
        else:correct=item.scope=='common'
        right+=correct;responses.append((item.a,item.b,correct));theta,se=adaptive.estimate(responses)
    return theta>=adaptive.GRADE_CUTS[grade]
result['strategies']={strategy:{g:{'passed':sum(simulate(strategy,g,s) for s in range(150)),'n':150} for g in GRADES} for strategy in ['longest','common_only']}
texts=[
 'Нужен middle backend Python, удалённая работа невозможна, только офис. Зарплата 150–200 тыс. руб.',
 'Нужен senior backend, наставничество junior-разработчиков. Python PostgreSQL.',
 'Нужен backend middle Python. Бюджет от 2000 до 3000 USD.',
 'Нужен backend middle Python, зарплата до 250 тыс. руб.',
 'Нужен frontend senior React, зарплата 200 000–300 000 рублей.',
]
result['independent_parser_examples']=[{'text':t,'parsed':asdict(parse_need(t))} for t in texts]
(OUT/'content-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
