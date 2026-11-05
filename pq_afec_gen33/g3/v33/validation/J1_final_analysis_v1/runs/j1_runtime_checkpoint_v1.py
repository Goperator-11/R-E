import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding='utf-8')
import json
from pathlib import Path
base=Path(r'C:\dev\codex_handoff\v33'); runs=base/'runs'
state_path=base/'state/LOOP_STATE.json'
state=json.loads(state_path.read_text(encoding='utf-8'))
progress_path=runs/'J1_joint_progress_04.json'
p=json.loads(progress_path.read_text(encoding='utf-8'))
assert state['iterations']==19 and state['current']=='J1'
t=state['tasks']['J1']; a=t['active_computation']
assert a['kind']=='CPU_development_MC' and a['family_sha256']==p['family_sha256'] and not p['errors']
a.update(progress_record=str(progress_path),last_checked_kst=p['recorded_kst'])
t['note']='J1 전체1500실행 수집과 합동3000실행 입력 검증을 마쳤다. 고정100행동 계산 PID20420을 진행 중이며 16결과·오류0이다. 상태7 후보는 아직 미채택이다.'
out=runs/'iter020_checkpoint_04.json'
value={'iteration':20,'recorded_kst':p['recorded_kst'],'task':'J1','note':t['note'],'active_computation':a}
with out.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
t['active_iteration_checkpoint']=str(out)
state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps(value,ensure_ascii=False))
