"""Local-trial tests use authored synthetic metadata; no user approval/model run."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import knowledge_pilot_trial as trial
import assemble_knowledge_pilot as assembly
from knowledge_export import canonical,digest,Rejection
from knowledge_export_v2_draft2_support import launch


def fixture():
    rid='urn:al-isabah:synthetic:record:1';raw='### $ 1 Synthetic Alpha\n~~ Synthetic retained paragraph.\n'
    unit={'id':'synthetic-unit-1','kind':'entry','sourceRecordVersionId':rid,'rawSha256':assembly.sha(raw.encode()),'spans':assembly.partition_unit('synthetic-unit-1',raw)}
    packet={'schema':'al-isabah.knowledge-pilot-input.v1','fixtureClass':'synthetic-conformance','issue':89,'sourceArtifactSha256':'1'*64,'candidateManifestSha256':'2'*64,'records':[{'id':rid,'sourceOrdinal':1,'sourceUnitIds':['synthetic-unit-1'],'retainedFindings':[{'category':'synthetic','priority':'review'}]}],'units':[unit],'policyPins':{p:assembly.lf_sha(ROOT/p) for p in assembly.POLICIES},'assemblerLfSha256':assembly.lf_sha(Path(assembly.__file__)),'packetSha256':''}
    packet['packetSha256']=digest({k:v for k,v in packet.items() if k!='packetSha256'})
    metadata={'packetSha256':packet['packetSha256'],'packetFileSha256':digest(packet),'sourceOrdinals':[1],'methodRegistrySha256':digest(trial.read(trial.method.REGISTRY_PATH)),'units':[{'id':unit['id'],'kind':unit['kind'],'sourceRecordVersionId':rid,'rawSha256':unit['rawSha256'],'spans':[{k:v for k,v in s.items() if k!='rawOpeniti'} for s in unit['spans']]}],'partitionSha256':''}
    metadata['partitionSha256']=digest({k:v for k,v in metadata.items() if k!='partitionSha256'})
    request=trial.decision_request(packet,metadata,'0'*40)
    decision={'schema':'al-isabah.knowledge-local-trial-decision.v1','request':request,'approval':'approved','origin':{'kind':'actual_user_message','threadId':trial.COORDINATOR,'userTurnReference':'synthetic-user-turn','recordedBy':'trusted_coordinator'}}
    return packet,metadata,decision


def partial_output(stage_input,packet):
    rid=packet['records'][0]['id'];sid=packet['units'][0]['spans'][0]['id'];concern='urn:al-isabah:synthetic:concern:1'
    return {'schema':'al-isabah.knowledge-pilot-stage-output.v1','stage':stage_input['stage'],'stageInputSha256':digest(stage_input),'packetSha256':packet['packetSha256'],'status':'partial','spanDispositions':[{'sourceSpanId':sid,'status':'unsupported_semantics','reasonCode':'unsupported','claimIds':[],'reportIds':[],'ambiguityGroupIds':[],'findingIds':[]}],'recordReviews':[{'sourceRecordVersionId':rid,**{k:'unresolved' for k in trial.REVIEW_AXES},'findingIds':[],'rationale':'Synthetic unresolved source and vocabulary checks.'}],'concerns':[{'id':concern,'sourceSpanIds':[sid],'category':'vocabulary','status':'open','rationale':'Synthetic unsupported meaning retained for review.'}],'retainedFindingCoverage':[{'sourceFindingId':trial.retained_ledger(packet)[0]['id'],'concernIds':[concern],'status':'retained'}],'mentionEvidence':[],'nonclaimReviews':[],**{k:[] for k in trial.COLLECTIONS}}


class KnowledgeLocalTrialTests(unittest.TestCase):
    def setUp(self):self.packet,self.metadata,self.decision=fixture();self.pin=digest(self.decision)
    def stage(self,stage=None,prior=()):return trial.prepare_stage(stage or trial.STAGES[0],self.decision,self.pin,self.packet,self.metadata,'0'*40,prior)
    def test_gate_accepts_only_exact_explicit_synthetic_decision(self):
        self.assertEqual(self.stage()['decisionSha256'],self.pin)
        for key,value in [('approval','pending'),('approval','denied')]:
            changed=copy.deepcopy(self.decision);changed[key]=value
            with self.assertRaisesRegex(Rejection,'trial-not-authorized'):trial.authorize(changed,digest(changed),self.packet,self.metadata,'0'*40)
    def test_no_real_decision_receipt_is_checked_in_or_generated(self):
        self.assertNotIn('approval',trial.decision_request(self.packet,self.metadata,'0'*40))
    def test_delegations_and_automatic_context_cannot_count_as_user_approval(self):
        for origin in ('agent_delegation','tool_output','automatic_continuation','scope_selection'):
            changed=copy.deepcopy(self.decision);changed['origin']['kind']=origin
            with self.assertRaisesRegex(Rejection,'trial-user-authorization-required'):trial.authorize(changed,digest(changed),self.packet,self.metadata,'0'*40)
    def test_external_decision_pin_and_scope_changes_fail(self):
        with self.assertRaisesRegex(Rejection,'trial-decision-pin-mismatch'):trial.authorize(self.decision,'f'*64,self.packet,self.metadata,'0'*40)
        for field,value in [('codeCommit','f'*40),('maxFreshWorkers',4),('publicReleaseAuthorized',True),('sourceOrdinals',[1,2])]:
            changed=copy.deepcopy(self.decision);changed['request'][field]=value
            with self.assertRaisesRegex(Rejection,'trial-decision-scope-mismatch'):trial.authorize(changed,digest(changed),self.packet,self.metadata,'0'*40)
    def test_real_packet_cannot_use_a_synthetic_decision(self):
        packet=copy.deepcopy(self.packet);packet.pop('fixtureClass');packet['records'][0]['sourceOrdinal']=10754
        packet['packetSha256']=digest({k:v for k,v in packet.items() if k!='packetSha256'})
        with self.assertRaises(Rejection):trial.authorize(self.decision,self.pin,packet,self.metadata,'0'*40)
    def test_partition_is_lossless_and_marks_only_explicit_paragraph_boundaries(self):
        raw='### $ 1 Heading and prose\n~~ continuation\n\n# Next paragraph\n~~ more\n'
        spans=assembly.partition_unit('synthetic-unit',raw)
        self.assertEqual(len(spans),2);self.assertEqual(''.join(s['rawOpeniti'] for s in spans),raw)
        self.assertIn('Heading and prose',spans[0]['rawOpeniti'])
    def test_packet_policy_and_partition_drift_rejected(self):
        packet=copy.deepcopy(self.packet);packet['units'][0]['spans'][0]['rawOpeniti']+='changed'
        with self.assertRaisesRegex(Rejection,'trial-packet-digest-mismatch'):trial.validate_packet(packet,self.metadata)
        with mock.patch.object(assembly,'lf_sha',return_value='f'*64):
            with self.assertRaisesRegex(Rejection,'trial-policy-drift'):trial.validate_packet(self.packet,self.metadata)
    def test_all_three_stages_capture_fresh_synthetic_host_metadata(self):
        prior=[];task=launch('codex-task','synthetic-pilot-task')
        for n,stage in enumerate(trial.STAGES):
            stage_input=self.stage(stage,prior);output=partial_output(stage_input,self.packet)
            receipt=trial.capture(stage_input,output,self.packet,self.pin,task,launch('codex-worker','synthetic-pilot-worker-'+str(n)),[p['receipt'] for p in prior])
            prior.append({'input':stage_input,'output':output,'receipt':receipt})
        self.assertEqual(len(prior),3);self.assertEqual(prior[-1]['output']['status'],'partial')
        self.assertNotIn('reviewed',canonical(prior[-1]['receipt']).decode())
        report=trial.final_report(self.decision,self.pin,self.packet,self.metadata,'0'*40,prior)
        self.assertEqual(report['status'],'partial');self.assertFalse(report['publicReleaseAuthorized'])
        self.assertEqual(report['counts']['blockedSpans'],1)
    def test_stage_skips_wrong_host_and_self_report_fail(self):
        with self.assertRaisesRegex(Rejection,'trial-stage-order-mismatch'):self.stage(trial.STAGES[1])
        stage=self.stage();output=partial_output(stage,self.packet);task=launch('codex-task','synthetic-task')
        for field,value in [('provider','unknown'),('reasoning','high'),('source','worker-self-report'),('firstTurn',False),('forked',True)]:
            worker=launch('codex-worker','synthetic-worker');worker['observed'][field]=value
            with self.assertRaisesRegex(Rejection,'trial-host-mismatch'):trial.capture(stage,output,self.packet,self.pin,task,worker,[])
    def test_worker_reuse_and_modified_previous_outputs_fail(self):
        stage=self.stage();output=partial_output(stage,self.packet);task=launch('codex-task','synthetic-task');worker=launch('codex-worker','synthetic-worker')
        receipt=trial.capture(stage,output,self.packet,self.pin,task,worker,[]);prior=[{'input':stage,'output':output,'receipt':receipt}]
        next_input=self.stage(trial.STAGES[1],prior)
        with self.assertRaisesRegex(Rejection,'trial-worker-independence-mismatch'):trial.capture(next_input,partial_output(next_input,self.packet),self.packet,self.pin,task,worker,[receipt])
        prior[0]['output']['recordReviews'][0]['rationale']='Changed after capture'
        with self.assertRaisesRegex(Rejection,'trial-receipt-binding-mismatch'):self.stage(trial.STAGES[1],prior)
    def test_missing_span_retained_finding_and_false_completion_fail(self):
        stage=self.stage()
        for change,code in [(lambda o:o['spanDispositions'].clear(),'trial-span-coverage-mismatch'),(lambda o:o['retainedFindingCoverage'].clear(),'trial-retained-finding-loss'),(lambda o:o.update(status='complete'),'trial-false-completion')]:
            output=partial_output(stage,self.packet);change(output)
            with self.assertRaisesRegex(Rejection,code):trial.validate_output(output,stage,self.packet)
    def test_exact_name_surface_evidence_and_no_fabricated_assessments(self):
        stage=self.stage();output=partial_output(stage,self.packet);rid=self.packet['records'][0]['id'];span=self.packet['units'][0]['spans'][0];surface='Synthetic Alpha';a=span['rawOpeniti'].index(surface);pin=assembly.sha(surface.encode())
        eid='urn:al-isabah:synthetic:entity:1';mid='urn:al-isabah:synthetic:mention:1';nid='urn:al-isabah:synthetic:name:1'
        output['entities']=[{'id':eid,'logicalEntityId':'urn:al-isabah:synthetic:logical-entity:1','kind':'person','sourceRecordVersionIds':[rid],'mentionIds':[mid],'nameIds':[nid],'identityAssessmentIds':[],'ambiguityGroupIds':[]}]
        output['mentions']=[{'id':mid,'entityId':eid,'sourceRecordVersionId':rid,'sourceSpanId':span['id'],'surfaceSha256':pin,'nameRole':'name','nameId':nid,'ambiguityGroupIds':[]}]
        output['names']=[{'id':nid,'entityId':eid,'language':'en','form':surface,'formRole':'name','derivation':'source_spelling','sourceRecordVersionId':rid,'sourceSpanId':span['id'],'sourceSurfaceSha256':pin,'assessmentIds':[],'ambiguityGroupIds':[]}]
        output['mentionEvidence']=[{'mentionId':mid,'sourceSpanId':span['id'],'startChar':a,'endChar':a+len(surface)}]
        trial.validate_output(output,stage,self.packet)
        output['mentionEvidence'][0]['startChar']+=1
        with self.assertRaisesRegex(Rejection,'trial-mention-evidence-mismatch'):trial.validate_output(output,stage,self.packet)
    def test_review_requires_positive_per_span_nonclaim_confirmation(self):
        stage=self.stage();output=partial_output(stage,self.packet);sid=output['spanDispositions'][0]['sourceSpanId']
        output['spanDispositions'][0].update(status='nonclaim_form',reasonCode='formula_only')
        with self.assertRaisesRegex(Rejection,'trial-nonclaim-review-missing'):trial.validate_output(output,stage,self.packet)
        output['nonclaimReviews']=[{'sourceSpanId':sid,'status':'proposed','rationale':'Synthetic proposed formula-only classification.'}]
        trial.validate_output(output,stage,self.packet)
        output['nonclaimReviews'][0]['status']='confirmed'
        with self.assertRaisesRegex(Rejection,'trial-nonclaim-review-missing'):trial.validate_output(output,stage,self.packet)

    def test_complete_trial_output_requires_all_positive_checks(self):
        stage=self.stage();output=partial_output(stage,self.packet);sid=output['spanDispositions'][0]['sourceSpanId']
        output['spanDispositions'][0].update(status='nonclaim_form',reasonCode='formula_only')
        output['nonclaimReviews']=[{'sourceSpanId':sid,'status':'proposed','rationale':'Synthetic classification proposed for separate review.'}]
        output['recordReviews'][0].update({key:'checked' for key in trial.REVIEW_AXES})
        output['concerns'][0]['status']='resolved';output['retainedFindingCoverage'][0]['status']='resolved';output['status']='complete'
        trial.validate_output(output,stage,self.packet)
        output['recordReviews'][0]['honorificPreservation']='unresolved'
        with self.assertRaisesRegex(Rejection,'trial-false-completion'):trial.validate_output(output,stage,self.packet)

    def test_checkout_gate_rejects_wrong_commit_and_modified_code(self):
        commit='a'*40
        with mock.patch.object(trial,'git',return_value=b'b'*40+b'\n'):
            with self.assertRaisesRegex(Rejection,'trial-code-commit-mismatch'):trial.verify_checkout(commit)
        with mock.patch.object(trial,'git',side_effect=[commit.encode()+b'\n',b'changed code']):
            with self.assertRaisesRegex(Rejection,'trial-code-worktree-drift'):trial.verify_checkout(commit)


    def test_real_proposal_rejects_synthetic_logical_identity(self):
        proposal={'entities':[{'id':'urn:al-isabah:trial:entity:1','logicalEntityId':'urn:al-isabah:trial:logical-entity:1'}]}
        trial.validate_real_identities(proposal)
        proposal['entities'][0]['logicalEntityId']='urn:al-isabah:synthetic:logical-entity:1'
        with self.assertRaisesRegex(Rejection,'trial-proposal-identity-mismatch'):trial.validate_real_identities(proposal)


    def test_runtime_output_cannot_be_written_into_public_tree(self):
        with self.assertRaisesRegex(Rejection,'trial-output-boundary-mismatch'):
            trial.require_runtime_directory(ROOT/'content'/'trial')
        with mock.patch.object(trial,'git',return_value=b''):
            trial.require_runtime_directory(ROOT/'.runtime/knowledge/issue-0089/synthetic')


    def test_existing_runtime_files_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'record.json';trial.write_new(path,{'id':1});trial.write_new(path,{'id':1})
            with self.assertRaisesRegex(Rejection,'trial-existing-output-conflict'):trial.write_new(path,{'id':2})
            self.assertEqual(path.read_bytes(),canonical({'id':1}))

if __name__=='__main__':unittest.main()
