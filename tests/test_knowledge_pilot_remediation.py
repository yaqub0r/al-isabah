"""Synthetic remediation rehearsals; no actual user approval or model execution."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from test_knowledge_pilot_trial import fixture,partial_output,launch
import knowledge_pilot_remediation as runner
from knowledge_export import digest,Rejection,read


def baseline_fixture():
    packet,metadata,decision=fixture();old=runner.old;stages=[]
    task=launch('codex-task','synthetic-old-task')
    for n,name in enumerate(old.STAGES):
        stage=old.prepare_stage(name,decision,digest(decision),packet,metadata,'0'*40,stages)
        output=partial_output(stage,packet)
        output['entities']=[{'id':'urn:al-isabah:synthetic:entity:baseline','logicalEntityId':'urn:al-isabah:synthetic:logical:baseline',
                             'kind':'person','sourceRecordVersionIds':[packet['records'][0]['id']],'mentionIds':[],
                             'nameIds':[],'identityAssessmentIds':[],'ambiguityGroupIds':[]}]
        receipt=old.capture(stage,output,packet,digest(decision),task,launch('codex-worker','synthetic-old-worker-'+str(n),'synthetic-old-task'),[x['receipt'] for x in stages])
        stages.append({'input':stage,'output':output,'receipt':receipt})
    report=old.final_report(decision,digest(decision),packet,metadata,'0'*40,stages)
    baseline=runner.baseline_value(stages,report,digest(report),packet)
    decision={**decision,'schema':'al-isabah.knowledge-remediation-decision.v1','request':runner.request(packet,metadata,'0'*40,baseline)}
    return packet,metadata,baseline,decision


def proposal(stage,packet):
    baseline=runner.baseline_output(stage['baseline']);output=partial_output(stage,packet)
    output['schema']='al-isabah.knowledge-pilot-stage-output.v2';output['entities']=copy.deepcopy(baseline['entities'])
    return {'schema':'al-isabah.knowledge-remediation-proposal.v1','output':output,'baselineSha256':stage['baselineSha256'],
            'concernOutcomes':[{'baselineConcernId':c['id'],'baselineConcernSha256':digest(c),'outcome':'residual',
                                'rationale':'Synthetic source limitation remains explicitly unresolved.'} for c in baseline['concerns']],
            'objectSuccessors':[]}


class KnowledgeRemediationTests(unittest.TestCase):
    def setUp(self):self.packet,self.metadata,self.baseline,self.decision=baseline_fixture();self.pin=digest(self.decision)
    def stage(self,name=None,prior=()):return runner.prepare(name or runner.old.STAGES[0],self.decision,self.pin,self.packet,self.metadata,'0'*40,self.baseline,prior)
    def test_three_stages_capture_envelope_and_preserve_baseline(self):
        original=digest(self.baseline);prior=[];task=launch('codex-task','synthetic-new-task')
        for n,name in enumerate(runner.old.STAGES):
            stage=self.stage(name,prior);value=proposal(stage,self.packet)
            receipt=runner.capture(stage,value,self.packet,self.pin,task,launch('codex-worker','synthetic-new-worker-'+str(n),'synthetic-new-task'),[x['receipt'] for x in prior])
            self.assertEqual(receipt['outputSha256'],digest(value));self.assertNotEqual(receipt['outputSha256'],digest(value['output']))
            prior.append({'input':stage,'proposal':value,'receipt':receipt})
        result=runner.report(self.decision,self.pin,self.packet,self.metadata,'0'*40,self.baseline,prior)
        self.assertEqual(result['status'],'partial');self.assertFalse(result['publicReleaseAuthorized']);self.assertFalse(result['consumerAdmissionAuthorized'])
        self.assertEqual(result['baselineReportSha256'],self.baseline['reportSha256']);self.assertEqual(digest(self.baseline),original)
    def test_baseline_drop_tamper_and_wrong_external_pin_fail(self):
        with self.assertRaisesRegex(Rejection,'remediation-baseline-pin-mismatch'):
            runner.baseline_value(self.baseline['stages'],self.baseline['report'],'f'*64,self.packet)
        changed=copy.deepcopy(self.baseline);changed['stages'][-1]['output']['concerns'][0]['rationale']='Changed historical evidence'
        with self.assertRaisesRegex(Rejection,'trial-receipt-binding-mismatch'):
            runner.baseline_value(changed['stages'],changed['report'],changed['reportSha256'],self.packet)
        changed=copy.deepcopy(self.baseline);changed['stages'].pop()
        with self.assertRaisesRegex(Rejection,'remediation-baseline-stage-mismatch'):
            runner.baseline_value(changed['stages'],changed['report'],changed['reportSha256'],self.packet)
    def test_old_authorization_and_agent_origin_are_not_new_approval(self):
        changed=copy.deepcopy(self.decision);changed['schema']='al-isabah.knowledge-local-trial-decision.v1'
        with self.assertRaisesRegex(Rejection,'remediation-new-decision-required'):
            runner.authorize(changed,digest(changed),self.packet,self.metadata,'0'*40,self.baseline)
        changed=copy.deepcopy(self.decision);changed['origin']['kind']='agent_delegation'
        with self.assertRaisesRegex(Rejection,'trial-user-authorization-required'):
            runner.authorize(changed,digest(changed),self.packet,self.metadata,'0'*40,self.baseline)
        self.assertNotIn('approval',runner.request(self.packet,self.metadata,'0'*40,self.baseline))
        for change in (lambda d:d.pop('approval'),lambda d:d['request'].update(maxFreshWorkers=4)):
            changed=copy.deepcopy(self.decision);change(changed)
            with self.assertRaises(Rejection):runner.authorize(changed,digest(changed),self.packet,self.metadata,'0'*40,self.baseline)
        changed=copy.deepcopy(self.decision);changed['origin']['userTurnReference']=''
        runner.authorize(changed,digest(changed),self.packet,self.metadata,'0'*40,self.baseline)
    def test_all_concerns_need_exact_hash_and_explicit_outcome(self):
        stage=self.stage()
        for change in (lambda v:v['concernOutcomes'].clear(),lambda v:v['concernOutcomes'][0].update(baselineConcernSha256='f'*64),
                       lambda v:v['concernOutcomes'][0].update(outcome='resolved'),lambda v:v['output']['concerns'][0].update(category='source'),
                       lambda v:v['concernOutcomes'][0].update(rationale=' ')):
            value=proposal(stage,self.packet);change(value)
            with self.assertRaises(Rejection):runner.validate_proposal(value,stage,self.packet)
        value=proposal(stage,self.packet);value['output']['concerns'][0]['id']+=':replacement';value['output']['retainedFindingCoverage'][0]['concernIds']=[value['output']['concerns'][0]['id']]
        with self.assertRaisesRegex(Rejection,'remediation-concern-loss'):runner.validate_proposal(value,stage,self.packet)
    def test_original_object_drop_or_changed_id_content_fails(self):
        stage=self.stage();value=proposal(stage,self.packet);value['output']['entities'].clear()
        with self.assertRaisesRegex(Rejection,'remediation-successor-mismatch'):runner.validate_proposal(value,stage,self.packet)
        value=proposal(stage,self.packet);value['output']['entities'][0]['logicalEntityId']+=':changed'
        with self.assertRaisesRegex(Rejection,'trial-immutable-id-conflict'):runner.validate_proposal(value,stage,self.packet)
    def test_explicit_successor_preserves_logical_identity_and_hash(self):
        stage=self.stage();value=proposal(stage,self.packet);old=value['output']['entities'][0];before=copy.deepcopy(old);old['id']+=':successor'
        value['objectSuccessors']=[{'before':{'kind':'entities','id':before['id']},'beforeSha256':digest(before),
                                    'after':{'kind':'entities','id':old['id']},'rationale':'Synthetic explicit successor.'}]
        runner.validate_proposal(value,stage,self.packet)
        changed=copy.deepcopy(value);changed['objectSuccessors'][0]['beforeSha256']='f'*64
        with self.assertRaisesRegex(Rejection,'remediation-successor-mismatch'):runner.validate_proposal(changed,stage,self.packet)
        changed=copy.deepcopy(value);changed['output']['entities'][0]['logicalEntityId']+=':other'
        with self.assertRaisesRegex(Rejection,'logical-identity-conflict'):runner.validate_proposal(changed,stage,self.packet)
    def test_historical_worker_reuse_and_stage_skips_fail(self):
        stage=self.stage();task=launch('codex-task','synthetic-new-task')
        worker=launch('codex-worker','synthetic-old-worker-0','synthetic-new-task')
        with self.assertRaisesRegex(Rejection,'remediation-historical-worker-reuse'):runner.capture(stage,proposal(stage,self.packet),self.packet,self.pin,task,worker,[])
        with self.assertRaisesRegex(Rejection,'trial-stage-order-mismatch'):self.stage(runner.old.STAGES[1])
    def test_prior_coverage_ledger_tamper_is_receipt_bound(self):
        stage=self.stage();value=proposal(stage,self.packet);task=launch('codex-task','synthetic-new-task')
        receipt=runner.capture(stage,value,self.packet,self.pin,task,launch('codex-worker','synthetic-new-worker','synthetic-new-task'),[])
        value['concernOutcomes'][0]['rationale']='Different independently valid residual description.'
        with self.assertRaisesRegex(Rejection,'trial-receipt-binding-mismatch'):
            self.stage(runner.old.STAGES[1],[{'input':stage,'proposal':value,'receipt':receipt}])
    def test_protected_directories_and_ancestors_are_rejected(self):
        root=runner.ROOT/'.runtime/knowledge/issue-0089';original=root/'trial';recovery=root/'adapter-recovery'
        with mock.patch.object(runner.old,'require_runtime_directory'):
            for directory in (original,original/'child',recovery,recovery/'child',root):
                with self.assertRaisesRegex(Rejection,'remediation-separate-directory-required'):runner.require_directories(directory,original,recovery)
            runner.require_directories(root/'new-synthetic-remediation',original,recovery)
    def test_cli_synthetic_request_and_prepare_use_new_directory(self):
        with tempfile.TemporaryDirectory(dir=runner.ROOT/'.runtime') as directory:
            root=Path(directory);original=root/'original';recovery=root/'recovery';new=root/'new'
            for n,item in enumerate(self.baseline['stages']):
                target=original if n==0 else recovery
                for key in ('input','output','receipt'):
                    runner.old.write_new(target/(runner.old.STAGES[n]+'.'+key+'.json'),item[key])
            runner.old.write_new(recovery/'recovery.json',{'receipt':self.baseline['stages'][0]['receipt']})
            runner.old.write_new(recovery/'validation-report.json',self.baseline['report'])
            runner.old.write_new(root/'packet.json',self.packet);runner.old.write_new(root/'partition.json',self.metadata)
            args=['runner','request','--packet',str(root/'packet.json'),'--partition',str(root/'partition.json'),
                  '--original-directory',str(original),'--recovery-directory',str(recovery),'--directory',str(new),
                  '--baseline-report-sha256',self.baseline['reportSha256']]
            with mock.patch.object(runner.old,'require_runtime_directory'),mock.patch.object(runner.old,'git',return_value=b'0'*40+b'\n'),mock.patch('sys.argv',args):
                self.assertEqual(runner.main(),0)
            self.assertEqual(read(new/'decision-request.json'),self.decision['request'])
            runner.old.write_new(root/'decision.json',self.decision)
            args[1]='prepare';args+=['--decision',str(root/'decision.json'),'--decision-sha256',self.pin,'--stage',runner.old.STAGES[0]]
            with mock.patch.object(runner.old,'require_runtime_directory'),mock.patch.object(runner.old,'git',return_value=b'0'*40+b'\n'),mock.patch('sys.argv',args):
                self.assertEqual(runner.main(),0)
            self.assertEqual(read(new/(runner.old.STAGES[0]+'.input.json')),self.stage())


if __name__=='__main__':unittest.main()
