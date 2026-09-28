"""Synthetic adapter recovery only; no real approval, capture, or model call."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from test_knowledge_pilot_trial import fixture,partial_output,launch
import knowledge_pilot_trial as trial
import knowledge_pilot_recovery as recovery
from knowledge_export import canonical,digest,Rejection


class KnowledgePilotRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.packet,self.metadata,decision=fixture()
        stage=trial.prepare_stage(trial.STAGES[0],decision,digest(decision),self.packet,self.metadata,'0'*40)
        output=partial_output(stage,self.packet)
        self.original={'decision':decision,'input':stage,'output':output,
                       'fileSha256':{k:digest(v) for k,v in [('decision',decision),('input',stage),('output',output)]}}
        self.review={'schema':'al-isabah.knowledge-local-trial-repair-review.v1',
                     'task':launch('codex-task','synthetic-task'),'worker':launch('codex-worker','synthetic-worker'),
                     'additionalWorkerTurnId':'metadata-followup','initialTurnOutputSha256':digest(output),
                     'initialTurnFinalized':True,'additionalTurnDisposition':'metadata_only_no_output_change'}
        # The original input retains old instructions while remaining stages use
        # a changed runbook at the repaired verifier commit.
        old_instructions=trial.RUNBOOK.read_bytes().replace(b'\r\n',b'\n')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        runbook=self.root/'runbook.md';runbook.write_bytes(old_instructions+b'\nSynthetic adapter repair instructions.\n')
        patch=mock.patch.object(trial,'RUNBOOK',runbook);patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(trial,'git',return_value=old_instructions);patch.start();self.addCleanup(patch.stop)
        scope=recovery.request(self.original,self.packet,self.metadata,'1'*40,self.review)
        self.decision={'schema':'al-isabah.knowledge-local-trial-repair-decision.v1','request':scope,
                       'approval':'approved','origin':{'kind':'trusted_coordinator_repair_review','threadId':trial.COORDINATOR}}
        self.pin=digest(self.decision)

    def args(self):return self.decision,self.pin,self.original,self.packet,self.metadata,'1'*40,self.review

    def capture(self):return recovery.capture_original(*self.args(),self.review['task'],self.review['worker'])

    def test_original_input_and_approval_stay_immutable_across_three_stage_recovery(self):
        before=canonical(self.original);captured=self.capture();prior=[]
        self.assertEqual(captured['kind'],'retrospective_verification_not_execution')
        self.assertEqual(captured['originalExecutionCodeCommit'],'0'*40)
        self.assertEqual(captured['verifierCodeCommit'],'1'*40)
        self.assertEqual(captured['receipt']['decisionSha256'],digest(self.original['decision']))
        for n,stage in enumerate(trial.STAGES[1:],1):
            stage_input=recovery.prepare(stage,*self.args(),captured,prior)
            self.assertEqual(stage_input['decisionSha256'],self.pin)
            self.assertNotEqual(stage_input['instructions'],self.original['input']['instructions'])
            self.assertEqual(stage_input['priorOutputs'][0],self.original['output'])
            # Realistic later coordinator turn metadata, same task launch/settings.
            task=copy.deepcopy(self.review['task']);task['observed'].update(turnId='later-'+str(n),firstTurn=False)
            worker=launch('codex-worker','synthetic-remaining-'+str(n))
            output=partial_output(stage_input,self.packet)
            receipt=trial.capture(stage_input,output,self.packet,self.pin,task,worker,[captured['receipt'],*[p['receipt'] for p in prior]])
            prior.append({'input':stage_input,'output':output,'receipt':receipt})
        self.assertEqual(canonical(self.original),before)
        self.assertEqual(len({captured['receipt']['worker']['observed']['sessionId'],*[x['receipt']['worker']['observed']['sessionId'] for x in prior]}),3)
        self.assertEqual(self.decision['request']['maxRemainingFreshWorkers'],2)

    def test_changed_original_bytes_even_with_identical_json_rejected(self):
        source=self.root/'original';source.mkdir()
        for key,name in [('decision','decision.json'),('input',recovery.STAGE+'.input.json'),('output',recovery.STAGE+'.output.json')]:
            (source/name).write_bytes(canonical(self.original[key]))
        before=recovery.original_files(source)
        self.assertEqual(before,self.original)
        output_path=source/(recovery.STAGE+'.output.json')
        output_path.write_text(json.dumps(self.original['output'],indent=2),encoding='utf-8')
        changed=recovery.original_files(source)
        self.assertEqual(changed['output'],before['output'])
        self.assertNotEqual(changed['fileSha256'],before['fileSha256'])
        with self.assertRaisesRegex(Rejection,'recovery-scope-mismatch'):
            recovery.authorize(self.decision,self.pin,changed,self.packet,self.metadata,'1'*40,self.review)

    def test_old_approval_cannot_be_relabeled_new_user_approval(self):
        changed=copy.deepcopy(self.decision);changed['origin']['kind']='actual_user_message'
        with self.assertRaisesRegex(Rejection,'recovery-coordinator-review-required'):
            recovery.authorize(changed,digest(changed),*self.args()[2:])
        changed=copy.deepcopy(self.original);changed['decision']['approval']='pending'
        with self.assertRaisesRegex(Rejection,'trial-not-authorized'):
            recovery.request(changed,self.packet,self.metadata,'1'*40,self.review)

    def test_wrong_decision_pin_and_scope_expansion_rejected(self):
        with self.assertRaisesRegex(Rejection,'recovery-decision-pin-mismatch'):
            recovery.authorize(self.decision,'f'*64,*self.args()[2:])
        for field,value in [('maxRemainingFreshWorkers',3),('rerunExtractionAuthorized',True),('originalDecisionSha256','f'*64),('originalCodeCommit','f'*40),('verifierCodeCommit','f'*40)]:
            changed=copy.deepcopy(self.decision);changed['request'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(Rejection,'recovery-scope-mismatch'):
                recovery.authorize(changed,digest(changed),*self.args()[2:])

    def test_later_or_unfinalized_output_cannot_claim_initial_turn(self):
        for field,value in [('initialTurnFinalized',False),('initialTurnOutputSha256','f'*64),('additionalTurnDisposition','semantic_continuation'),('additionalWorkerTurnId','turn')]:
            review=copy.deepcopy(self.review);review[field]=value
            with self.assertRaisesRegex(Rejection,'recovery-initial-turn-review-required'):
                recovery.request(self.original,self.packet,self.metadata,'1'*40,review)
        worker=copy.deepcopy(self.review['worker']);worker['observed'].update(turnId='metadata-followup',firstTurn=False)
        with self.assertRaisesRegex(Rejection,'recovery-launch-mismatch'):
            recovery.capture_original(*self.args(),self.review['task'],worker)

    def test_wrong_worker_parent_and_unreviewed_launch_rejected(self):
        worker=copy.deepcopy(self.review['worker']);worker['observed']['parentSessionId']='other'
        with self.assertRaisesRegex(Rejection,'trial-worker-parent-mismatch'):
            trial.capture(self.original['input'],self.original['output'],self.packet,digest(self.original['decision']),self.review['task'],worker,[])
        with self.assertRaisesRegex(Rejection,'recovery-launch-mismatch'):
            recovery.capture_original(*self.args(),self.review['task'],launch('codex-worker','other-worker'))

    def test_reused_workers_and_changed_parent_settings_rejected(self):
        captured=self.capture();stage=recovery.prepare(trial.STAGES[1],*self.args(),captured)
        output=partial_output(stage,self.packet)
        with self.assertRaisesRegex(Rejection,'trial-worker-independence-mismatch'):
            trial.capture(stage,output,self.packet,self.pin,self.review['task'],self.review['worker'],[captured['receipt']])
        for field,value in [('sessionId','other-task'),('model','wrong'),('reasoning','high'),('provider','other'),('forked',True)]:
            task=copy.deepcopy(self.review['task']);task['observed'][field]=value
            with self.subTest(field=field),self.assertRaises(Rejection):
                trial.capture(stage,output,self.packet,self.pin,task,launch('codex-worker','fresh',task['observed']['sessionId']),[captured['receipt']])

    def test_recovery_cannot_rerun_extraction_skip_review_or_replace_evidence(self):
        captured=self.capture()
        for stage in (trial.STAGES[0],trial.STAGES[2]):
            with self.assertRaisesRegex(Rejection,'recovery-stage-order-mismatch'):
                recovery.prepare(stage,*self.args(),captured)
        changed=copy.deepcopy(captured);changed['verifierCodeCommit']='2'*40
        with self.assertRaisesRegex(Rejection,'recovery-receipt-mismatch'):
            recovery.prepare(trial.STAGES[1],*self.args(),changed)
        original=copy.deepcopy(self.original);original['input']['instructions']='changed'
        with self.assertRaisesRegex(Rejection,'recovery-original-input-mismatch'):
            recovery.request(original,self.packet,self.metadata,'1'*40,self.review)

    def test_cli_recovery_and_remaining_stages_use_observed_current_parent_turns(self):
        original_dir=self.root/'original-cli';original_dir.mkdir();directory=self.root/'recovered-cli'
        for key,name in [('decision','decision.json'),('input',recovery.STAGE+'.input.json'),('output',recovery.STAGE+'.output.json')]:
            (original_dir/name).write_bytes(canonical(self.original[key]))
        review_path=self.root/'review.json';review_path.write_bytes(canonical(self.review))
        decision_path=self.root/'decision.json';decision_path.write_bytes(canonical(self.decision))
        task_request=self.root/'task-request.json';task_request.write_bytes(canonical(self.review['task']['request']))
        worker_request=self.root/'worker-request.json';worker_request.write_bytes(canonical(self.review['worker']['request']))
        task_log=self.root/'task.jsonl';worker_log=self.root/'worker.jsonl'
        def logs(worker,turn):
            task_rows=[{'type':'session_meta','payload':{'id':'synthetic-task','model_provider':'openai'}},
                       {'type':'turn_context','payload':{'turn_id':'turn','model':'gpt-5.6-sol','effort':'xhigh'}}]
            if turn!='turn':task_rows.append({'type':'turn_context','payload':{'turn_id':turn,'model':'gpt-5.6-sol','effort':'xhigh'}})
            worker_rows=[{'type':'session_meta','payload':{'id':worker,'session_id':'synthetic-task','parent_thread_id':'synthetic-task','source':{'subagent':{'thread_spawn':{'parent_thread_id':'synthetic-task'}}},'model_provider':'openai'}},
                         {'type':'turn_context','payload':{'turn_id':'turn','model':'gpt-5.6-sol','effort':'xhigh'}}]
            if worker=='synthetic-worker':worker_rows.append({'type':'turn_context','payload':{'turn_id':'metadata-followup','model':'gpt-5.6-sol','effort':'xhigh'}})
            for path,rows in [(task_log,task_rows),(worker_log,worker_rows)]:path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            return ['--task-log',str(task_log),'--worker-log',str(worker_log),'--task-request',str(task_request),'--worker-request',str(worker_request),'--task-session','synthetic-task','--task-turn',turn,'--worker-session',worker,'--worker-turn','turn']
        packet_path=self.root/'packet.json';packet_path.write_bytes(canonical(self.packet))
        metadata_path=self.root/'metadata.json';metadata_path.write_bytes(canonical(self.metadata))
        common=['--original-directory',str(original_dir),'--directory',str(directory),'--review',str(review_path),'--packet',str(packet_path),'--partition',str(metadata_path),'--decision',str(decision_path),'--decision-sha256',self.pin]
        def run(action,*extra):
            def git(*args):return b'1'*40+b'\n' if args[0]=='rev-parse' else self.original['input']['instructions'].encode()
            with mock.patch.object(trial,'git',side_effect=git),mock.patch.object(trial,'require_runtime_directory'),mock.patch('sys.argv',['recovery.py',action,*common,*extra]),mock.patch('sys.stdout'):
                self.assertEqual(recovery.main(),0,action)
        run('request')
        self.assertEqual(trial.read(directory/'repair-request.json'),self.decision['request'])
        run('capture-original',*logs('synthetic-worker','turn'))
        for n,stage in enumerate(trial.STAGES[1:],1):
            run('prepare','--stage',stage)
            stage_input=trial.read(directory/(stage+'.input.json'))
            (directory/(stage+'.output.json')).write_bytes(canonical(partial_output(stage_input,self.packet)))
            run('capture','--stage',stage,*logs('synthetic-cli-worker-'+str(n),'later-'+str(n)))
        run('report')
        report=trial.read(directory/'validation-report.json')
        self.assertEqual(len(report['stageReceiptSha256']),3)
        self.assertEqual(report['status'],'partial');self.assertFalse(report['consumerAdmissionAuthorized'])
        self.assertEqual(recovery.original_files(original_dir),self.original)

    def test_separate_explicit_directory_required(self):
        base=trial.ROOT/'.runtime/knowledge/issue-0089/trial'
        with self.assertRaisesRegex(Rejection,'recovery-separate-directory-required'):recovery.require_directories(base,base)
        with self.assertRaisesRegex(Rejection,'trial-output-boundary-mismatch'):recovery.require_directories(base,trial.ROOT/'content')
        recovery.require_directories(base,base.parent/'repair')
        with mock.patch('sys.argv',['knowledge_pilot_recovery.py','request']),mock.patch('sys.stderr'):
            with self.assertRaises(SystemExit) as error:recovery.main()
        self.assertEqual(error.exception.code,2)


if __name__=='__main__':unittest.main()
