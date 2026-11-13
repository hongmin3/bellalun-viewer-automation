"""REQ-FOLLOWUP-004: a verified interrupted restore can unblock the next run without a PASS or deletion."""
from contextlib import nullcontext
import json
from types import SimpleNamespace

import pytest

from core.run_preservation import RunPreservation
from tools import recover_preservation as cli


@pytest.mark.parametrize('fault', [None, 'services', 'source_changed', 'backup_changed', 'proof_write',
                                  'receipt_write', 'completed_record', 'normal_proof', 'orphan_normal_proof', 'cleanup_pending'])
def test_interrupted_recovery_finalizes_only_after_verified_persisted_recovery(tmp_path, monkeypatch, fault):
    from core import execution_session
    from core.dbreset import APP_SERVICES
    from core import run_preservation as storage_module
    from bellalunauto import runtime
    import run
    image=tmp_path/'Image'
    image.mkdir()
    (image/'existing').write_bytes(b'original')
    store=tmp_path/'store'
    store.mkdir()
    workspace=tmp_path/'work'
    session=RunPreservation(workspace,'interrupted',{'Image':image},restore_after=True,
                            storage_dir=store,require_finalization=True)
    session.prepare()
    (image/'generated').write_bytes(b'generated')
    session.finalize()
    if fault=='backup_changed': (store/'interrupted/before/Image/existing').write_bytes(b'bad-backup')
    if fault=='normal_proof': session._save('verified',normal_completion_before_cleanup={'run_id':'interrupted'})
    if fault=='orphan_normal_proof': (session.run_dir/'cleanup-completion.json').write_text('{}',encoding='utf-8')
    if fault=='cleanup_pending': (session.run_dir/'image-cleanup-pending.json').write_text('{}',encoding='utf-8')
    receipt=workspace/'Runs/interrupted/run.json'
    receipt.parent.mkdir(parents=True)
    original={'run_id':'interrupted','status':'completed' if fault=='completed_record' else 'stopped',
              'action':'run-regression','exit_code':0 if fault=='completed_record' else 130,
              'plan':{'restore_after':True},'reports':[]}
    receipt.write_text(json.dumps(original),encoding='utf-8')
    if fault=='source_changed': (image/'existing').write_bytes(b'changed-after-restore')
    monkeypatch.setattr(runtime,'RunLock',lambda:nullcontext())
    monkeypatch.setattr(run,'Context',lambda *a:SimpleNamespace(cfg={}))
    monkeypatch.setattr(execution_session,'stop_product',lambda *a:None)
    monkeypatch.setattr(execution_session,'DatabasePreservation',lambda *a:None)
    monkeypatch.setattr(execution_session,'start_services',lambda:{n:'STOPPED' if fault=='services' else 'RUNNING' for n in APP_SERVICES})
    real_write=storage_module._write_json
    def write(path,value):
        if fault=='receipt_write' and path==receipt: raise OSError('receipt persistence failed')
        if fault=='proof_write' and path.name=='interrupted-recovery.json': raise OSError('proof persistence failed')
        return real_write(path,value)
    monkeypatch.setattr(storage_module,'_write_json',write)
    def forbidden(*a,**k): raise AssertionError('interrupted runs must retain generated images')
    monkeypatch.setattr(RunPreservation,'cleanup_generated_images',forbidden)
    code=cli.main(['--workspace',str(workspace),'--run-id','interrupted','--config','unused','--apply'])
    record=json.loads(receipt.read_text(encoding='utf-8'))
    assert record['status']==original['status'] and record['exit_code']==original['exit_code']
    assert any(p.read_bytes()==b'generated' for p in image.parent.glob('.Image.bellalun-*-quarantine/*') if p.is_file())
    if fault is None:
        assert code==0
        assert RunPreservation.pending(workspace)==[]
        assert record['restoration']['status']=='verified'
        proof=json.loads((session.run_dir/'interrupted-recovery.json').read_text(encoding='utf-8'))
        assert proof['normal_completion'] is False
        assert proof['restoration']['image_cleanup']['status']=='skipped'
    else:
        assert code!=0
        assert RunPreservation.pending(workspace)==['interrupted']


@pytest.mark.parametrize('database_matches',[True,False])
@pytest.mark.parametrize('exit_code',[1,3])
def test_finalization_rechecks_database_without_repeating_its_restore(tmp_path,monkeypatch,database_matches,exit_code):
    from core import execution_session
    from core.dbreset import APP_SERVICES
    from bellalunauto import runtime
    import run
    class Database:
        matches=True
        restore_calls=0
        def backup(self,folder):
            (folder/'fixture.bak').write_bytes(b'database-original')
            return {'scope':'synthetic DB state'}
        def verify_backup(self,*args): return True
        def restore(self,*args): self.restore_calls+=1
        def verify_restored(self,*args): return self.matches
    database=Database()
    source=tmp_path/'Image'
    source.mkdir()
    (source/'existing').write_bytes(b'original')
    store=tmp_path/'store'
    store.mkdir()
    workspace=tmp_path/'work'
    session=RunPreservation(workspace,'interrupted',{'Image':source},restore_after=True,
                            storage_dir=store,require_finalization=True,db_adapter=database)
    session.prepare()
    session.finalize()
    assert database.restore_calls==1
    database.matches=database_matches
    receipt=workspace/'Runs/interrupted/run.json'
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'run_id':'interrupted','status':'abnormal','exit_code':exit_code,
        'action':'run-regression','plan':{'restore_after':True},'reports':[]}),encoding='utf-8')
    monkeypatch.setattr(runtime,'RunLock',lambda:nullcontext())
    monkeypatch.setattr(run,'Context',lambda *a:SimpleNamespace(cfg={}))
    monkeypatch.setattr(execution_session,'DatabasePreservation',lambda *a:database)
    monkeypatch.setattr(execution_session,'stop_product',lambda *a:None)
    monkeypatch.setattr(execution_session,'start_services',lambda:{n:'RUNNING' for n in APP_SERVICES})
    code=cli.main(['--workspace',str(workspace),'--run-id','interrupted','--config','unused','--apply'])
    assert code==(0 if database_matches else 2)
    assert database.restore_calls==1
    assert RunPreservation.pending(workspace)==([] if database_matches else ['interrupted'])
    assert json.loads(receipt.read_text(encoding='utf-8'))['status']=='abnormal'
