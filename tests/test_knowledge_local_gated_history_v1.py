"""Synthetic completed gated lineage; no real source corpus or model calls."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[1]/'tests')]
import knowledge_gated_continuation as gated
import knowledge_local_gated_history_v1 as history_adapter
from knowledge_export import digest,Rejection
import test_knowledge_gated_continuation as continuation_fixture
import knowledge_local_gated_projection_v1 as gated_projection
import knowledge_local_projection as old_projection
import knowledge_export_local_gated_v1 as gated_export


class GatedHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):continuation_fixture.ContinuationTests.setUpClass()

    def setUp(self):
        source=continuation_fixture.ContinuationTests('test_failed_launch_consumes_budget_and_extraction_is_retained')
        source.setUp();self.addCleanup(source.doCleanups);self.source=source
        self.original_commit=source.commit;self.corrected_commit='f'*40
        name=gated.REVIEW
        stage=gated.prepare(name,source.ctx,source.log,source.commit,source.decision,source.pin)
        proposal=source.fixture.proposal(stage,source.ctx['first']['proposal']['output'])
        gated.original.old.write_new(source.workdir/'decision-request.json',source.req)
        gated.original.old.write_new(source.workdir/'approved-decision.json',source.decision)
        gated.original.old.write_new(source.workdir/(name+'.input.json'),stage)
        reserved=gated.reserve_once(source.workdir,name,source.ctx,source.log,source.commit,source.decision,source.pin)
        worker_log=source.worker_log('synthetic-replacement-review',phase='final_answer')
        with mock.patch.object(gated,'terminal_result',return_value=('unknown',None)):
            unknown=gated.bind_once(source.workdir,name,worker_log,'synthetic-replacement-review',
                                    'turn',source.ctx,source.log,source.commit,source.decision,source.pin)
        gated.original.old.write_new(source.workdir/(name+'.proposal.json'),proposal)
        evidence={'requestSha256':digest(source.req),'decisionSha256':source.pin,
                  'inputSha256':digest(stage),'reservationSha256':digest(reserved),
                  'originalUnknownAttemptSha256':digest(unknown),'proposalSha256':digest(proposal),
                  'logSha256':hashlib.sha256(worker_log.read_bytes()).hexdigest(),
                  'workerSessionId':'synthetic-replacement-review','workerTurnId':'turn',
                  'hostTerminalPhase':'final_answer','hostTerminalStatus':'completed',
                  'reclassifiedAttemptSha256':digest({**unknown,'status':'completed'})}
        def git(*args):
            if args==('rev-parse','HEAD'):return ('d'*40+'\n').encode() # descendant HEAD
            return (gated.ROOT/args[1].split(':',1)[1]).read_bytes()
        self.git=mock.patch.object(gated.original.old,'git',side_effect=git)
        self.git.start();self.addCleanup(self.git.stop)
        with (mock.patch.object(gated,'review_correction_preview',return_value=evidence),
              mock.patch.object(gated,'REVIEW_CORRECTION_PINS',
                                {'request':digest(source.req),'decision':source.pin})):
            repair=gated.repair_document(source.ctx,source.log,self.corrected_commit,source.decision,source.pin)
        repair['status']='reviewed';repair_pin=digest(repair)
        source.ctx.update(repair=repair,repairPin=repair_pin);source.commit=self.corrected_commit
        self.repair_check=mock.patch.object(gated,'validate_repair',return_value=repair)
        self.repair_check.start();self.addCleanup(self.repair_check.stop)
        review={'input':stage,'proposal':proposal,'reservation':reserved,'attempt':unknown,'receipt':None}
        review['receipt']=gated.capture(name,review,source.ctx,source.log,source.commit,
                                        source.decision,source.pin,unknown['worker'])
        adj=source.adjudication(review,remove=True)
        report=gated.report(source.ctx,source.log,source.commit,source.decision,source.pin,review,adj)
        ctx=copy.deepcopy(source.ctx);ctx.pop('repair');ctx.pop('repairPin')
        self.history={'schema':history_adapter.SCHEMA,'context':ctx,'failedLogPath':str(source.log.resolve()),
                      'continuationRequest':copy.deepcopy(source.req),'continuationDecision':copy.deepcopy(source.decision),
                      'repair':copy.deepcopy(repair),'review':copy.deepcopy(review),
                      'adjudication':copy.deepcopy(adj),'report':copy.deepcopy(report)}
        self.pins={'originalRequestSha256':digest(ctx['request']),'originalDecisionSha256':digest(ctx['decision']),
                   'continuationRequestSha256':digest(source.req),'continuationDecisionSha256':source.pin,
                   'repairSha256':repair_pin,'reviewUnknownAttemptSha256':digest(unknown),
                   'finalProposalSha256':digest(adj['proposal']),'finalLedgerSha256':digest(adj['ledger']),
                   'finalGateSha256':digest(adj['gate']),'finalReportSha256':digest(report)}

    def test_descendant_head_replays_three_successes_and_four_launches(self):
        result=history_adapter.validate_history(self.history,self.pins)
        self.assertEqual(result['schema'],history_adapter.NORMALIZED)
        self.assertEqual(len(result['stages']),3)
        self.assertEqual(result['stageDecisionSha256'],[digest(self.source.ctx['decision']),self.source.pin,self.source.pin])
        self.assertEqual([x['status'] for x in result['report']['launchAttempts']],
                         ['completed','failed_capacity','completed','completed'])
        self.assertEqual(result['stages'][1]['attempt']['status'],'unknown')
        self.assertEqual(result['report']['finalKnownCoverageStatus'],'not_established')

    def test_initial_and_cumulative_projection_keep_source_identity_and_partial_state(self):
        records=sorted(r['id'] for r in self.source.ctx['packet']['records'])
        initial=old_projection.project_history(self.source.ctx['history'],records)
        current=gated_projection.project_history(self.history,self.pins,records,initial[3])
        repeated=gated_projection.project_history(self.history,self.pins,records,initial[3])
        self.assertEqual(current,repeated)
        self.assertEqual(current[1],initial[1])
        self.assertEqual(current[2],initial[2])
        self.assertEqual(current[3]['priorBundle'],initial[3])
        self.assertEqual(len(current[3]['receipts']),len(initial[3]['receipts'])+3)
        self.assertEqual([r['sourceDecisionSha256'] for r in current[3]['receipts'][-3:]],
                         [digest(self.source.ctx['decision']),self.source.pin,self.source.pin])
        self.assertTrue(any(x['status']=='partial' for x in current[3]['completionDerivation']))
        self.assertTrue(all(x['status']=='unreviewed' for x in current[0]['assessments']
                            if x['kind']=='human_review'))
        self.assertEqual(gated_projection.validate_projection(*current),
                         {r['id']:r for r in current[3]['receipts']})
        candidate=gated_export.candidate(self.history,self.pins,records,initial[3])
        self.assertEqual(candidate[:4],current)
        self.assertEqual(candidate[4]['schemaId'],'al-isabah.knowledge-export.v2-local1')
        self.assertFalse(candidate[6]['consumerAdmissionAuthorized'])
        self.assertEqual(candidate[4]['coverage']['requestedLogicalRecords'],len(records))
        self.assertEqual(candidate[4]['coverage']['dependencyLogicalRecords'],0)
        self.assertGreater(len(current[0]['lifecycleEvents']),len(initial[0]['lifecycleEvents']))
        projected={r['id']:r for r in current[0]['sourceRecords']}
        for source_record in self.source.ctx['packet']['records']:
            expected=old_projection.identity('logical-record',
                [current[2]['authority']['revisionId'],source_record['sourceOrdinal']],versioned=False)
            self.assertEqual(projected[source_record['id']]['logicalRecordId'],expected)

    def test_final_receipt_covers_retained_retired_historical_finding(self):
        records=sorted(r['id'] for r in self.source.ctx['packet']['records'])
        original=old_projection.stage_snapshot
        retained_id=old_projection.identity('synthetic-retained-finding','indirect-target')
        retired_id=old_projection.identity('synthetic-retired-finding','historical-only')
        injected={}

        def with_historical_finding(item,packet,inventory,source_records,profile,index,classifications=None):
            stage=original(item,packet,inventory,source_records,profile,index,classifications)
            if index==0:
                retained=copy.deepcopy(stage['findings'][0]);retained['id']=retained_id
                retained['targets']=[{'kind':'ambiguityGroups','id':stage['ambiguityGroups'][0]['id']}]
                injected['retained']=retained
                retired=copy.deepcopy(stage['findings'][0]);retired['id']=retired_id
                stage['findings'].extend([retained,retired])
            if index==2:stage['findings'].append(copy.deepcopy(injected['retained']))
            return stage

        with mock.patch.object(gated_projection.prior_projection,'stage_snapshot',
                               side_effect=with_historical_finding):
            candidate=gated_export.candidate(self.history,self.pins,records)
            normalized=history_adapter.validate_history(self.history,self.pins)
            packet=normalized['packet'];profile=candidate[2]
            inventory,source_records=old_projection.inventory_value(packet,profile,records)
            classes=old_projection.baseline_classifications(normalized['baseline'],packet,
                old_projection.read(old_projection.BASELINE_CLASSIFICATIONS),
                old_projection.BASELINE_CLASSIFICATIONS_SHA256)
            next_stage=old_projection.stage_snapshot(normalized['stages'][-1],packet,inventory,
                                                      source_records,profile,2,classes)
        snapshot,bundle=candidate[0],candidate[3]
        self.assertEqual(bundle['projectionVersion'],gated_projection.PROJECTION_VERSION)
        raw_finding=copy.deepcopy(next(f for f in next_stage['findings'] if f['id']==retained_id))
        raw_prior_stage=copy.deepcopy(next_stage)
        gated_projection.bind_finding_source_owners(raw_prior_stage,packet,{retained_id:raw_finding})
        self.assertEqual(next(f for f in raw_prior_stage['findings'] if f['id']==retained_id),raw_finding)
        known={f['id']:f for f in snapshot['findings']}
        gated_projection.bind_finding_source_owners(next_stage,packet,known)
        old_projection.merge_objects(next_stage['findings'],snapshot['findings'])
        incompatible=copy.deepcopy(known[retained_id])
        incompatible['category']='identity' if incompatible['category']!='identity' else 'omission'
        with self.assertRaisesRegex(Rejection,'gated-finding-prior-identity-conflict'):
            gated_projection.bind_finding_source_owners(copy.deepcopy(raw_prior_stage),packet,
                {retained_id:incompatible})
        self.assertIn(retained_id,{f['id'] for f in snapshot['findings']})
        self.assertIn(retired_id,{f['id'] for f in snapshot['findings']})
        self.assertTrue(any({'kind':'findings','id':retired_id} in event['targets']
                            for event in snapshot['lifecycleEvents']))
        final_objects={(item['ref']['kind'],item['ref']['id'])
                       for item in bundle['bindings'][-1]['outputs']['objects']}
        self.assertIn(('findings',retained_id),final_objects)
        self.assertNotIn(('findings',retired_id),final_objects)
        self.assertEqual(candidate[4]['coverage']['requestedLogicalRecords'],len(records))

    def test_pinned_lineage_tampering_rejected(self):
        for mutate in (lambda h:h['report']['launchAttempts'][1].update(status='completed'),
                       lambda h:h['review']['attempt'].update(status='completed'),
                       lambda h:h['repair'].update(status='pending_review'),
                       lambda h:h['adjudication']['reservation'].update(slotNumber=3),
                       lambda h:h['adjudication']['proposal']['output']['recordReviews'][0].update(rationale='forged')):
            changed=copy.deepcopy(self.history);mutate(changed)
            with self.assertRaises(Rejection):history_adapter.validate_history(changed,self.pins)
        changed=copy.deepcopy(self.history);changed['report']['launchAttempts'][1]['status']='completed'
        pins={**self.pins,'finalReportSha256':digest(changed['report'])}
        with self.assertRaisesRegex(Rejection,'gated-history-report-drift'):
            history_adapter.validate_history(changed,pins)
        changed=copy.deepcopy(self.history);changed['repair']['status']='pending_review'
        pins={**self.pins,'repairSha256':digest(changed['repair'])}
        with self.assertRaisesRegex(Rejection,'gated-history-scope-mismatch'):
            history_adapter.validate_history(changed,pins)

    def test_changed_historical_code_or_terminal_log_rejected(self):
        actual_git=gated.original.old.git
        def drift(*args):
            if args[0]=='show' and args[1].endswith(':'+gated.CODE):return b'changed historical runner'
            return actual_git(*args)
        with mock.patch.object(gated.original.old,'git',side_effect=drift):
            with self.assertRaisesRegex(Rejection,'gated-history-code-drift'):
                history_adapter.validate_history(self.history,self.pins)
        log=Path(self.history['review']['attempt']['logPath']);original=log.read_bytes()
        try:
            log.write_bytes(original.replace(b'"error": null',b'"error": {"message": "capacity"}'))
            with self.assertRaises(Rejection):history_adapter.validate_history(self.history,self.pins)
        finally:log.write_bytes(original)


if __name__=='__main__':unittest.main()
