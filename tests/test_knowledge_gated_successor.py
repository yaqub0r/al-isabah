"""Fictional gated-successor conformance; no actual authorization or worker."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[1]/'tests')]
import knowledge_gated_successor as successor
from test_knowledge_local_sol_high_history import sol_history,sol_launch
from knowledge_export import digest,read,Rejection


class GatedSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history=sol_history()
        cls.packet=cls.history['stages'][0]['input']['lockedInput']
        cls.partition=cls.history['partition']
        cls.final=cls.history['stages'][-1]['proposal']['output']
        cls.history_pin=digest(cls.history);cls.report_pin=digest(cls.history['report'])
        cls.output_pin=digest(cls.final);cls.commit='f'*40
        report=next(r for r in cls.final['reports'] if r['id'] in cls.final['events'][0]['reportIds'])
        cls.span_id=report['sourceSpanIds'][0]
        cls.record_id=cls.final['events'][0]['sourceRecordVersionIds'][0]
        cls.seed={'schema':'al-isabah.knowledge-coverage-seed.v1','status':'reviewed_for_gate',
                  'sourceArtifactSha256':cls.packet['sourceArtifactSha256'],
                  'packetSha256':cls.packet['packetSha256'],'baselineOutputSha256':cls.output_pin,
                  'profileSha256':digest(read(successor.remediation.PROFILE)),
                  'originReportSha256':cls.report_pin,
                  'requestedSourceRecordVersionIds':sorted(r['id'] for r in cls.packet['records']),
                  'obligations':[{'id':'O-SYNTHETIC-NEW-ACT','recordId':cls.record_id,
                                  'sourceSpanIds':[cls.span_id],'kind':'semantic_gap',
                                  'originSha256':cls.report_pin,
                                  'allowedUnresolvedReasons':['not_yet_extracted'],
                                  'expectedSemantics':[{'kind':'events','semanticId':'urn:al-isabah:event-type:death'}]}]}
        cls.seed_pin=digest(cls.seed)

    def setUp(self):
        self.code=mock.patch.object(successor,'verify_committed_code')
        self.code.start();self.addCleanup(self.code.stop)
        self.args=(self.packet,self.partition,self.history,self.seed,self.commit,self.history_pin,
                   self.report_pin,self.output_pin,self.seed_pin)
        self.req=successor.request(*self.args)
        self.decision={'schema':successor.DECISION_SCHEMA,'request':self.req,'approval':'approved',
                       'origin':{'kind':'actual_user_message','threadId':successor.old.COORDINATOR,
                                 'userTurnReference':'SYNTHETIC-CONFORMANCE-ONLY',
                                 'recordedBy':'trusted_coordinator'}}
        self.pin=digest(self.decision)
        self.task=sol_launch('codex-task','synthetic-successor-task')

    def stage(self,name,prior):
        return successor.prepare(name,self.decision,self.pin,*self.args,prior)

    def proposal(self,stage,previous,add_event=False):
        output=copy.deepcopy(previous);output['stage']=stage['stage'];output['stageInputSha256']=digest(stage)
        if add_event:
            event=copy.deepcopy(self.final['events'][0]);event['id']='urn:al-isabah:trial:conformance:events:new-death'
            event['typeId']='urn:al-isabah:event-type:death';output['events'].append(event)
        return {'schema':'al-isabah.knowledge-remediation-proposal.v1','output':output,
                'baselineSha256':stage['baselineSha256'],'objectSuccessors':[],
                'concernOutcomes':[{'baselineConcernId':c['id'],'baselineConcernSha256':digest(c),
                                    'outcome':'resolved' if c['status']=='resolved' else 'residual',
                                    'rationale':'Synthetic conformance only.'} for c in self.final['concerns']]}

    def first(self):
        stage=self.stage(successor.old.STAGES[0],[])
        proposal=self.proposal(stage,self.final,True)
        span=next(s for u in self.packet['units'] for s in u['spans'] if s['id']==self.span_id)
        raw=span['rawOpeniti'];anchor={'id':'synthetic-anchor-1','recordId':self.record_id,
            'sourceSpanId':self.span_id,'startChar':0,'endChar':len(raw),
            'surfaceSha256':hashlib.sha256(raw.encode('utf-8')).hexdigest(),'scope':'coarse'}
        ledger={'schema':'al-isabah.knowledge-coverage-ledger.v1',
                **{k:self.seed[k] for k in ('sourceArtifactSha256','packetSha256','baselineOutputSha256','profileSha256')},
                'seedSha256':self.seed_pin,'candidateOutputSha256':digest(proposal['output']),
                'sourceAnchors':[anchor],
                'outcomes':[{'obligationId':'O-SYNTHETIC-NEW-ACT','status':'represented',
                             'objectRefs':[{'kind':'events','id':proposal['output']['events'][-1]['id']}],
                             'sourceAnchorIds':[anchor['id']],'reasonCode':''}]}
        gate=successor.gate_result(self.packet,self.partition,self.history,self.seed,stage,proposal,ledger,self.req)
        binding={'proposalSha256':digest(proposal),'ledgerSha256':digest(ledger),
                 'gateResultSha256':digest(gate),'firstReceiptSha256':''}
        receipt=successor.capture(stage,proposal,self.packet,self.pin,self.task,
            sol_launch('codex-worker','synthetic-successor-worker-1','synthetic-successor-task'),[],binding,ledger,gate)
        return {'input':stage,'proposal':proposal,'ledger':ledger,'gate':gate,'receipt':receipt}

    def chain(self):
        first=self.first();prior=[first]
        for n,name in enumerate(successor.old.STAGES[1:],2):
            stage=self.stage(name,prior);proposal=self.proposal(stage,prior[-1]['proposal']['output'])
            if name==successor.old.STAGES[2]:
                ledger=copy.deepcopy(first['ledger'])
                ledger['candidateOutputSha256']=digest(proposal['output'])
                evidence=successor.final_reconciliation(self.packet,self.partition,self.history,self.seed,
                           stage,proposal,ledger,self.req,stage['gateBinding'])
            else:ledger=evidence=None
            receipt=successor.capture(stage,proposal,self.packet,self.pin,self.task,
                sol_launch('codex-worker','synthetic-successor-worker-'+str(n),'synthetic-successor-task'),
                [x['receipt'] for x in prior],stage['gateBinding'],final_ledger=ledger,final_evidence=evidence)
            item={'input':stage,'proposal':proposal,'receipt':receipt}
            if ledger is not None:item.update(ledger=ledger,gate=evidence)
            prior.append(item)
        return prior

    def test_three_stage_chain_is_partial_and_gate_bound(self):
        stages=self.chain()
        self.assertEqual(stages[0]['gate']['status'],'partial_progress')
        self.assertEqual(stages[1]['input']['gateBinding']['firstReceiptSha256'],stages[0]['receipt']['receiptSha256'])
        self.assertEqual(stages[1]['input']['extractionEvidence']['ledger'],stages[0]['ledger'])
        self.assertEqual(stages[2]['input']['extractionEvidence']['gateResult'],stages[0]['gate'])
        value=successor.report(self.decision,self.pin,*self.args,stages)
        self.assertEqual(value['status'],'partial')
        self.assertEqual(value['finalKnownCoverageStatus'],'retained_partial_progress')
        self.assertFalse(value['exhaustiveCoverage'])
        self.assertFalse(value['consumerAdmissionAuthorized'])
        self.assertFalse(value['publicReleaseAuthorized'])
        self.assertEqual(value['humanReview'],'unreviewed')

    def test_missing_or_changed_gate_blocks_later_stages(self):
        first=self.first()
        for key in ('gate','ledger','proposal','receipt'):
            item=copy.deepcopy(first)
            if key=='gate':item.pop('gate')
            elif key=='ledger':item['ledger']['outcomes'][0]['sourceAnchorIds']=[]
            elif key=='proposal':item['proposal']['output']['events'][-1]['typeId']='urn:al-isabah:event-type:marriage'
            else:item['receipt']['gateResultSha256']='0'*64
            with self.assertRaises((Rejection,KeyError)):
                self.stage(successor.old.STAGES[1],[item])

    def test_exact_request_seed_and_decision_required(self):
        other=copy.deepcopy(self.decision);other['request']['seedSha256']='0'*64
        with self.assertRaises(Rejection):successor.prepare(successor.old.STAGES[0],other,digest(other),*self.args)
        with self.assertRaises(Rejection):successor.prepare(successor.old.STAGES[0],self.decision,'0'*64,*self.args)
        with self.assertRaises(Rejection):successor.request(*self.args[:-1],'0'*64)

    def test_old_worker_and_wrong_host_settings_rejected(self):
        first=self.first();stage=first['input'];proposal=first['proposal'];ledger=first['ledger'];gate=first['gate']
        binding={'proposalSha256':digest(proposal),'ledgerSha256':digest(ledger),
                 'gateResultSha256':digest(gate),'firstReceiptSha256':''}
        old_worker=copy.deepcopy(self.history['stages'][0]['receipt']['worker'])
        with self.assertRaises(Rejection):successor.capture(stage,proposal,self.packet,self.pin,self.task,
            old_worker,[],binding,ledger,gate)
        for field,value in [('model','gpt-5.6-sol'),('reasoning','xhigh'),('parentSessionId','other-task')]:
            worker=sol_launch('codex-worker','synthetic-successor-worker-other','synthetic-successor-task')
            worker['observed'][field]=value
            with self.assertRaises(Rejection):successor.capture(stage,proposal,self.packet,self.pin,self.task,
                worker,[],binding,ledger,gate)
        forked=sol_launch('codex-worker','synthetic-successor-worker-forked','synthetic-successor-task')
        forked['request']['overrides']['fork_turns']='all'
        with self.assertRaises(Rejection):successor.capture(stage,proposal,self.packet,self.pin,self.task,
            forked,[],binding,ledger,gate)

    def test_seed_owned_span_and_later_receipt_drift_fail(self):
        bad=copy.deepcopy(self.seed)
        bad['obligations'][0]['sourceSpanIds']=['urn:missing-span']
        with self.assertRaises(Rejection):successor.request(self.packet,self.partition,self.history,bad,
            self.commit,self.history_pin,self.report_pin,self.output_pin,digest(bad))
        stages=self.chain();stages[-1]['receipt']['firstProposalSha256']='0'*64
        with self.assertRaises(Rejection):successor.report(self.decision,self.pin,*self.args,stages)

    def test_final_rejection_cannot_claim_extraction_progress(self):
        stages=self.chain();final=stages[-1];stage=final['input']
        proposal=self.proposal(stage,self.final)
        ledger=copy.deepcopy(final['ledger']);ledger['candidateOutputSha256']=digest(proposal['output'])
        ledger['outcomes'][0].update(status='unresolved',objectRefs=[],sourceAnchorIds=[],reasonCode='not_yet_extracted')
        evidence=successor.final_reconciliation(self.packet,self.partition,self.history,self.seed,
                    stage,proposal,ledger,self.req,stage['gateBinding'])
        self.assertEqual(evidence['status'],'not_established')
        receipt=successor.capture(stage,proposal,self.packet,self.pin,self.task,
            sol_launch('codex-worker','synthetic-successor-worker-3','synthetic-successor-task'),
            [x['receipt'] for x in stages[:2]],stage['gateBinding'],final_ledger=ledger,final_evidence=evidence)
        stages[-1]={'input':stage,'proposal':proposal,'ledger':ledger,'gate':evidence,'receipt':receipt}
        report=successor.report(self.decision,self.pin,*self.args,stages)
        self.assertEqual(report['extractionGateStatus'],'partial_progress')
        self.assertEqual(report['finalKnownCoverageStatus'],'not_established')
        self.assertEqual(report['finalMaterialObligationIds'],[])

    def test_nested_historical_worker_reuse_rejected(self):
        first=self.first();stage=first['input'];proposal=first['proposal']
        binding={'proposalSha256':digest(proposal),'ledgerSha256':digest(first['ledger']),
                 'gateResultSha256':digest(first['gate']),'firstReceiptSha256':''}
        prior_id=self.history['baseline']['stages'][0]['receipt']['worker']['observed']['sessionId']
        worker=sol_launch('codex-worker',prior_id,'synthetic-successor-task')
        self.assertIn(prior_id,stage['baseline']['historicalWorkerSessionIds'])
        with self.assertRaisesRegex(Rejection,'successor-historical-worker-reuse'):
            successor.capture(stage,proposal,self.packet,self.pin,self.task,worker,[],binding,
                              first['ledger'],first['gate'])

    def test_history_verifier_checkout_drift_rejected(self):
        self.code.stop()
        def fake_git(*args):
            if args==('rev-parse','HEAD'):return (self.commit+'\n').encode()
            path=args[1].split(':',1)[1]
            return b'drift' if path=='scripts/knowledge_local_execution.py' else (successor.ROOT/path).read_bytes()
        with mock.patch.object(successor.old,'git',side_effect=fake_git):
            with self.assertRaisesRegex(Rejection,'trial-code-worktree-drift'):
                successor.verify_committed_code(self.commit)
            with mock.patch.object(successor,'validate_baseline') as baseline:
                with self.assertRaisesRegex(Rejection,'trial-code-worktree-drift'):
                    successor.request(*self.args)
                baseline.assert_not_called()

    def test_review_context_and_final_ledger_tampering_rejected(self):
        stages=self.chain()
        altered=copy.deepcopy(stages)
        altered[1]['input']['extractionEvidence']['ledger']['outcomes'][0]['status']='unresolved'
        with self.assertRaises(Rejection):successor.report(self.decision,self.pin,*self.args,altered)
        altered=copy.deepcopy(stages)
        altered[-1]['ledger']['outcomes'][0]['objectRefs']=[]
        with self.assertRaises(Rejection):successor.report(self.decision,self.pin,*self.args,altered)


if __name__=='__main__':unittest.main()
