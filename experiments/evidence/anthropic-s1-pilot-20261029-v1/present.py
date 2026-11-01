"""Create a readable complete response report and branch-blinded review packet.

This is an analysis artifact, not an external effect or semantic adjudication.
"""
import json
import hashlib
import os
import random
import sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def create_text(path, text):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:
        f.write(text);f.flush();os.fsync(f.fileno())
    fd=os.open(ROOT,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def main():
    if any((ROOT/name).exists() for name in ('full-answers-report.md','blind-review-packet.json','blind-review-mapping-private.json','human-first-packet.md')):
        raise ValueError('output artifacts already exist; create a successor instead')
    summary=json.loads((ROOT/'model-summary.json').read_text())
    tasks={x['case_id']:x for x in json.loads((ROOT/'tasks-frozen.json').read_text())}
    rubric=json.loads((ROOT/'rubric-frozen.json').read_text())
    contract=json.loads((ROOT/'model-contract.json').read_text())
    contract_sha=hashlib.sha256((ROOT/'model-contract.json').read_bytes()).hexdigest()
    challenge=json.loads((ROOT/'model-challenge.json').read_text())
    dispatch=json.loads((ROOT/'model-dispatch.json').read_text())
    if challenge.get('contract_sha256')!=contract_sha or dispatch.get('contract_sha256')!=contract_sha:
        raise ValueError('contract binding mismatch')
    if dispatch.get('challenge_sha256')!=hashlib.sha256((ROOT/'model-challenge.json').read_bytes()).hexdigest():
        raise ValueError('challenge binding mismatch')
    for fn,key in (('tasks-frozen.json','tasks_sha256'),('rubric-frozen.json','rubric_sha256')):
        if hashlib.sha256((ROOT/fn).read_bytes()).hexdigest()!=contract[key]:raise ValueError('frozen input mismatch')
    allowed={(x['case_id'],x['arm']) for x in contract['schedule']}
    records=summary['records']; indexed={}
    for record in records:
        raw=(ROOT/record['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('outcome hash mismatch')
        obj=json.loads(raw);key=(obj['case_id'],obj['arm'])
        if key!=(record['case_id'],record['arm']) or key not in allowed or key in indexed:raise ValueError('outcome binding mismatch')
        indexed[key]=obj['outcome']
    db=sqlite3.connect('file:'+str(ROOT/'ledger/ledger.sqlite3')+'?mode=ro',uri=True)
    try:
        rows=db.execute('select id,kind,state,http_status,actual_micro,quote_micro from effects').fetchall()
        ledger=db.execute('select stopped,exposure_micro,generation_attempts,count_attempts,source_attempts from run').fetchone()
    finally: db.close()
    names=('stopped','exposure_micro','generation_attempts','count_attempts','source_attempts')
    if tuple(summary['ledger'][n] for n in names)!=ledger:raise ValueError('summary ledger mismatch')
    derived=contract['caps']['prior_micro']+sum(actual if actual is not None else quote for _,_,_,_,actual,quote in rows)
    if derived!=ledger[1]:raise ValueError('exposure inconsistent with effects')
    gen_cost=sum((actual or 0) for ident,kind,state,http,actual,quote in rows if kind=='generation' and actual is not None)
    source_cost=sum((actual or 0) for ident,kind,state,http,actual,quote in rows if kind=='source' and actual is not None)
    uncertain=[{'kind':k,'state':s,'http_status':h,'reserved_micro':q} for ident,k,s,h,a,q in rows if s in ('started','uncertain') or (s=='succeeded' and a is None)]
    arm_costs={a:0 for a in ('A','B','C','probe')}
    for case_id in tasks:
        for arm in arm_costs:
            slot=hashlib.sha256(json.dumps({'case_id':case_id,'arm':arm,'pilot':'anthropic-s1-v1'},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            arm_costs[arm]+=sum((actual or 0) for ident,kind,state,http,actual,quote in rows if kind=='generation' and ident.startswith('generation:'+slot+':') and actual is not None)
    if sum(arm_costs.values())!=gen_cost:raise ValueError('unattributed generation cost')
    lines=['# Anthropic S-1: полные ответы пилотного сравнения',
        '', 'Статус: исследовательский разбор; оценка смысловой корректности и человеческой самостоятельности не является автоматически установленной.',
        '', 'A — обычная модель; B — явная проверка от противного; C — SI-style оркестрация. Полные структурированные результаты приведены ниже. Ошибки и отсутствующие ответы не заменены предположениями.',
        '', f"Назначений записано: {len(records)} из 18. Gemini-расход по usage: ${gen_cost/1e6:.6f}; источник: ${source_cost/1e6:.6f}. Прежняя консервативная экспозиция: $56.609714; текущая: ${summary['ledger']['exposure_micro']/1e6:.6f} / $60. Счёт провайдера отдельно не сверён.",
        '', 'Рыночные выдержки Polymarket: индексированные тексты, полный актуальный раздел правил не подтверждён напрямую. Входы, полный модельный след, raw-ответы и статусы сохранены в этом каталоге.', '']
    case_order=list(tasks)
    blind=[];mapping={}; rng=random.Random(292610)
    for case_index,cid in enumerate(case_order,1):
        task=tasks[cid];lines.extend([f'## Случай {case_index}: {cid}', '', task['question'], ''])
        order=['A','B','C'];rng.shuffle(order)
        blind_answers=[]
        for slot,arm in enumerate(order,1):
            anon=f'{case_index:02d}-{slot:02d}';mapping[anon]={'case_id':cid,'arm':arm}
            out=indexed.get((cid,arm)); answer=None if out is None else out.get('result') or out.get('final_result')
            status='missing' if out is None else ('usable' if answer else ('unknown' if out.get('status')=='unknown' else 'technical_failure'))
            blind_answers.append({'response_id':anon,'status':status,'answer':answer})
        blind.append({'case_id':cid,'task':task,'responses':blind_answers})
        for arm in ('A','B','C'):
            out=indexed.get((cid,arm));lines += [f'### {arm}', '']
            if out is None:lines+=['Не выполнено.', ''];continue
            lines += [f"Статус: `{out.get('status')}`; причина: `{out.get('reason')}`; вызовов: {out.get('calls')}", '']
            answer=out.get('result') or out.get('final_result')
            if answer:
                lines += [answer.get('answer','[Нет текстового поля answer]'), '', 'Полная структура ответа:', '', '```json',json.dumps(answer,ensure_ascii=False,indent=2),'```','']
            else:
                lines += ['Полного итогового ответа нет. Причина и все промежуточные результаты сохранены в отдельном outcome-файле.', '']
                returned=[e.get('result') for e in out.get('events',[]) if e.get('event')=='model_returned' and e.get('stage')=='formatter']
                returned += [e.get('response') for e in out.get('responses',[]) if isinstance(e.get('response'),dict)]
                if returned:
                    lines += ['Последний сырой структурированный ответ (не прошёл проверку и не является итоговым ответом):','','```json',json.dumps(returned[-1],ensure_ascii=False,indent=2),'```','']
    lines += ['## Технический учёт', '', f'Оценка по usage: A ${arm_costs["A"]/1e6:.6f}; B ${arm_costs["B"]/1e6:.6f}; C ${arm_costs["C"]/1e6:.6f}; проверки посылок ${arm_costs["probe"]/1e6:.6f}; источник ${source_cost/1e6:.6f}.', '', f'Всего записанных попыток в новом журнале: {len(rows)}; неопределённых или незавершённых: {len(uncertain)}.',
              '', 'Эта сумма модельных расходов рассчитана по provider usage, а не подтверждена инвойсом. Текущая экспозиция включает прежние неразрешённые резервы; её нельзя считать фактически оплаченными затратами.', '']
    assignments=json.loads((ROOT/'human-assignment-private.json').read_text())
    if hashlib.sha256((ROOT/'human-assignment-private.json').read_bytes()).hexdigest()!=contract['human_assignment_sha256']:
        raise ValueError('human assignment binding mismatch')
    human=['# Один ответ модели на каждый вопрос', '',
      'До просмотра остальных вариантов запишите по каждому случаю: что изменилось в вашем суждении, что повлияло, какие альтернативы вы видите и что хотели бы проверить. Изменить мнение допустимо.',
      '', 'Вопросы и исходные материалы доступны в tasks-frozen.json. Имена ветвей намеренно не показаны.', '']
    for index,item in enumerate(assignments,1):
        cid,arm=item['case_id'],item['first_arm'];out=indexed.get((cid,arm));answer=None if out is None else out.get('result') or out.get('final_result')
        human += [f'## Вопрос {index}: {cid}', '',tasks[cid]['question'],'']
        if answer:human += [answer.get('answer','[Ответ без текстового поля]'),'']
        else:human += ['Ответ не получен или завершился техническим сбоем; не считайте это содержательным суждением.','']
    create_text(ROOT/'human-first-packet.md','\n'.join(human))
    create_text(ROOT/'full-answers-report.md','\n'.join(lines))
    create_text(ROOT/'blind-review-packet.json',json.dumps({'cases':blind,'rubric':rubric},ensure_ascii=False,indent=2))
    create_text(ROOT/'blind-review-mapping-private.json',json.dumps(mapping,ensure_ascii=False,indent=2))
    print('prepared full report and branch-blind review packet; cases',len(blind),'recorded',len(records))

if __name__=='__main__':main()
