"""Synthetic capacity failure and bounded successor continuation; no model calls."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[1]/'tests')]
import knowledge_gated_continuation as continuation
import test_knowledge_gated_successor as fixtures
from test_knowledge_local_sol_high_history import sol_launch
from knowledge_export import digest,Rejection


class ContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.GatedSuccessorTests.setUpClass()

    def setUp(self):
        self.fixture=fixtures.GatedSuccessorTests('test_three_stage_chain_is_partial_and_gate_bound')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.patchers=[mock.patch.object(continuation,'ORIGINAL_COMMIT',self.fixture.commit),
                       mock.patch.object(continuation,'verify_historical_code'),
                       mock.patch.object(continuation,'verify_current_code'),
                       mock.patch.object(continuation,'FAILED_SESSION','synthetic-failed-review'),
                       mock.patch.object(continuation,'FAILED_TURN','synthetic-failed-turn')]
        for patcher in self.patchers:patcher.start();self.addCleanup(patcher.stop)
        first=self.fixture.first()
        self.ctx={'request':self.fixture.req,'decision':self.fixture.decision,'first':first,
                  'reviewInput':self.fixture.stage(continuation.REVIEW,[first]),
                  'packet':self.fixture.packet,'partition':self.fixture.partition,
                  'history':self.fixture.history,'seed':self.fixture.seed}
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.log=Path(self.temporary.name)/'failed.jsonl'
        self.workdir=Path(self.temporary.name)/'continuation'
        self.ctx['continuationDirectory']=str(self.workdir.resolve())
        self.write_log()
        self.log_patch=mock.patch.object(continuation,'FAILED_LOG_SHA',hashlib.sha256(self.log.read_bytes()).hexdigest())
        self.log_patch.start();self.addCleanup(self.log_patch.stop)
        self.commit='e'*40
        self.req=continuation.request(self.ctx,self.log,self.commit)
        self.decision={'schema':continuation.DECISION_SCHEMA,'request':self.req,'approval':'approved',
                       'origin':{'kind':'actual_user_message','threadId':continuation.original.old.COORDINATOR,
                                 'userTurnReference':'SYNTHETIC-SUPPLEMENT-ONLY','recordedBy':'trusted_coordinator'}}
        self.pin=digest(self.decision)

    def write_log(self,error=None,model='gpt-6-sol',final=False):
        parent=self.ctx['first']['receipt']['task']['observed']['sessionId']
        rows=[{'type':'session_meta','payload':{'id':'synthetic-failed-review','session_id':parent,
               'parent_thread_id':parent,'source':{'subagent':{'thread_spawn':{'parent_thread_id':parent}}},
               'model_provider':'openai'}},
              {'type':'turn_context','payload':{'turn_id':'synthetic-failed-turn','model':model,'effort':'high'}},
              {'type':'event_msg','payload':{'type':'task_complete','turn_id':'synthetic-failed-turn',
               'error':{'message':error or continuation.FAILED_ERROR}}}]
        if final:rows.append({'type':'response_item','payload':{'type':'message','role':'assistant','phase':'final','content':[]}})
        self.log.write_text(''.join(json.dumps(x)+'\n' for x in rows),encoding='utf-8')

    def worker_log(self,session,failed=False,unknown=False,phase='final'):
        parent=self.ctx['first']['receipt']['task']['observed']['sessionId']
        rows=[{'type':'session_meta','payload':{'id':session,'session_id':parent,
               'parent_thread_id':parent,'source':{'subagent':{'thread_spawn':{'parent_thread_id':parent}}},
               'model_provider':'openai'}},
              {'type':'turn_context','payload':{'turn_id':'turn','model':'gpt-6-sol','effort':'high'}}]
        if not failed and not unknown:
            rows.append({'type':'response_item','payload':{'type':'message','role':'assistant',
                         'phase':phase,'content':[]}})
        if not unknown:
            rows.append({'type':'event_msg','payload':{'type':'task_complete','turn_id':'turn',
                         'error':{'message':continuation.FAILED_ERROR} if failed else None}})
        path=Path(self.temporary.name)/(session+'.jsonl')
        path.write_text(''.join(json.dumps(x)+'\n' for x in rows),encoding='utf-8')
        return path

    def slot(self,name,stage,review=None,session=None,failed=False,unknown=False):
        continuation.original.old.write_new(self.workdir/(name+'.input.json'),stage)
        reserved=continuation.reserve_once(self.workdir,name,self.ctx,self.log,self.commit,
                                            self.decision,self.pin,review)
        log=self.worker_log(session or 'synthetic-'+name,failed,unknown)
        attempt=continuation.bind_once(self.workdir,name,log,session or 'synthetic-'+name,'turn',
                                        self.ctx,self.log,self.commit,self.decision,self.pin,review)
        return reserved,attempt

    def review(self):
        stage=continuation.prepare(continuation.REVIEW,self.ctx,self.log,self.commit,self.decision,self.pin)
        proposal=self.fixture.proposal(stage,self.ctx['first']['proposal']['output'])
        reserved,attempt=self.slot(continuation.REVIEW,stage,session='synthetic-replacement-review')
        item={'input':stage,'proposal':proposal,'reservation':reserved,'attempt':attempt,'receipt':None}
        item['receipt']=continuation.capture(continuation.REVIEW,item,self.ctx,self.log,self.commit,
                                              self.decision,self.pin,attempt['worker'])
        return item

    def adjudication(self,review,remove=False):
        stage=continuation.prepare(continuation.ADJUDICATION,self.ctx,self.log,self.commit,
                                   self.decision,self.pin,review)
        previous=self.fixture.final if remove else review['proposal']['output']
        proposal=self.fixture.proposal(stage,previous)
        ledger=copy.deepcopy(self.ctx['first']['ledger'])
        ledger['candidateOutputSha256']=digest(proposal['output'])
        if remove:
            ledger['outcomes'][0].update(status='unresolved',objectRefs=[],sourceAnchorIds=[],reasonCode='not_yet_extracted')
        evidence=continuation.final_evidence(self.ctx,stage,proposal,ledger,self.req)
        reserved,attempt=self.slot(continuation.ADJUDICATION,stage,review,
                                   session='synthetic-continuation-adjudicator')
        item={'input':stage,'proposal':proposal,'ledger':ledger,'gate':evidence,
              'reservation':reserved,'attempt':attempt,'receipt':None}
        item['receipt']=continuation.capture(continuation.ADJUDICATION,item,self.ctx,self.log,
                        self.commit,self.decision,self.pin,attempt['worker'],review)
        return item

    def test_failed_launch_consumes_budget_and_extraction_is_retained(self):
        self.assertEqual(self.req['maxAdditionalWorkerLaunches'],2)
        self.assertEqual(self.req['maxTotalWorkerLaunches'],4)
        self.assertEqual([x['status'] for x in continuation.attempts(self.ctx,self.req)],['completed','failed_capacity'])
        review=self.review()
        self.assertEqual(review['input']['priorOutputs'],[self.ctx['first']['proposal']['output']])
        self.assertEqual(review['input']['extractionEvidence']['ledger'],self.ctx['first']['ledger'])
        self.assertEqual(review['receipt']['failedLaunchSha256'],self.req['failedLaunchSha256'])
        wrong=copy.deepcopy(review['attempt']['worker'])
        wrong['observed']['sessionId']='synthetic-unbound-worker'
        with self.assertRaisesRegex(Rejection,'continuation-attempt-worker-mismatch'):
            continuation.capture(continuation.REVIEW,review,self.ctx,self.log,self.commit,
                                 self.decision,self.pin,wrong)
        adjudication=self.adjudication(review)
        result=continuation.report(self.ctx,self.log,self.commit,self.decision,self.pin,review,adjudication)
        self.assertEqual(len(result['launchAttempts']),4)
        self.assertEqual(result['finalKnownCoverageStatus'],'retained_partial_progress')
        self.assertEqual(result['launchAttempts'][1]['status'],'failed_capacity')
        self.assertEqual(result['launchAttempts'][2]['attemptSha256'],digest(review['attempt']))
        self.assertEqual(result['launchAttempts'][3]['reservationSha256'],digest(adjudication['reservation']))
        self.assertFalse(result['consumerAdmissionAuthorized'])

    def test_failed_replacement_consumes_slot_and_blocks_advancement(self):
        stage=continuation.prepare(continuation.REVIEW,self.ctx,self.log,self.commit,self.decision,self.pin)
        reserved,attempt=self.slot(continuation.REVIEW,stage,session='synthetic-failed-replacement',failed=True)
        self.assertEqual(reserved['slotNumber'],3)
        self.assertEqual(attempt['status'],'failed_capacity')
        with self.assertRaisesRegex(Rejection,'continuation-slot-already-consumed'):
            continuation.reserve_once(self.workdir,continuation.REVIEW,self.ctx,self.log,self.commit,
                                      self.decision,self.pin)
        with self.assertRaisesRegex(Rejection,'continuation-slot-already-consumed'):
            continuation.bind_once(self.workdir,continuation.REVIEW,self.worker_log('synthetic-retry'),
                                   'synthetic-retry','turn',self.ctx,self.log,self.commit,self.decision,self.pin)
        alternate=Path(self.temporary.name)/'alternate-continuation'
        continuation.original.old.write_new(alternate/(continuation.REVIEW+'.input.json'),stage)
        with self.assertRaisesRegex(Rejection,'continuation-directory-mismatch'):
            continuation.reserve_once(alternate,continuation.REVIEW,self.ctx,self.log,self.commit,
                                      self.decision,self.pin)
        rebound=copy.deepcopy(self.ctx);rebound['continuationDirectory']=str(alternate.resolve())
        with self.assertRaises(Rejection):
            continuation.prepare(continuation.REVIEW,rebound,self.log,self.commit,self.decision,self.pin)
        proposal=self.fixture.proposal(stage,self.ctx['first']['proposal']['output'])
        item={'input':stage,'proposal':proposal,'reservation':reserved,'attempt':attempt,'receipt':None}
        with self.assertRaisesRegex(Rejection,'continuation-attempt-not-completed'):
            continuation.capture(continuation.REVIEW,item,self.ctx,self.log,self.commit,
                                 self.decision,self.pin,attempt['worker'])
        with self.assertRaises(Rejection):
            continuation.prepare(continuation.ADJUDICATION,self.ctx,self.log,self.commit,
                                 self.decision,self.pin,item)

    def test_unknown_slot_and_wrong_bound_session_fail_closed(self):
        stage=continuation.prepare(continuation.REVIEW,self.ctx,self.log,self.commit,self.decision,self.pin)
        reserved,attempt=self.slot(continuation.REVIEW,stage,session='synthetic-unknown-review',unknown=True)
        self.assertEqual(attempt['status'],'unknown')
        proposal=self.fixture.proposal(stage,self.ctx['first']['proposal']['output'])
        item={'input':stage,'proposal':proposal,'reservation':reserved,'attempt':attempt,'receipt':None}
        with self.assertRaisesRegex(Rejection,'continuation-attempt-not-completed'):
            continuation.capture(continuation.REVIEW,item,self.ctx,self.log,self.commit,
                                 self.decision,self.pin,attempt['worker'])
        changed=copy.deepcopy(attempt['worker']);changed['observed']['sessionId']='different-session'
        with self.assertRaises(Rejection):
            continuation.capture(continuation.REVIEW,item,self.ctx,self.log,self.commit,
                                 self.decision,self.pin,changed)

    def test_host_final_answer_then_matching_successful_terminal_is_completed(self):
        stage=continuation.prepare(continuation.REVIEW,self.ctx,self.log,self.commit,self.decision,self.pin)
        continuation.original.old.write_new(self.workdir/(continuation.REVIEW+'.input.json'),stage)
        reserved=continuation.reserve_once(self.workdir,continuation.REVIEW,self.ctx,self.log,
                                            self.commit,self.decision,self.pin)
        path=self.worker_log('synthetic-final-answer',phase='final_answer')
        rows=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(rows[-1]['payload']['error'],None)
        attempt=continuation.bind_once(self.workdir,continuation.REVIEW,path,'synthetic-final-answer','turn',
                   self.ctx,self.log,self.commit,self.decision,self.pin)
        self.assertEqual(attempt['status'],'completed')
        self.assertEqual(continuation.terminal_result(path.read_bytes(),'turn'),('completed','final_answer'))
        changed=copy.deepcopy(rows);changed[-1]['payload']['turn_id']='another-turn'
        with self.assertRaises(Rejection):
            continuation.terminal_result(''.join(json.dumps(x)+'\n' for x in changed).encode(),'turn')

    def test_failed_launch_with_final_answer_cannot_be_called_no_output(self):
        self.write_log(final=True)
        rows=[json.loads(x) for x in self.log.read_text(encoding='utf-8').splitlines()]
        rows[-1]['payload']['phase']='final_answer'
        self.log.write_text(''.join(json.dumps(x)+'\n' for x in rows),encoding='utf-8')
        with mock.patch.object(continuation,'FAILED_LOG_SHA',hashlib.sha256(self.log.read_bytes()).hexdigest()):
            with self.assertRaisesRegex(Rejection,'continuation-failure-not-proven'):
                continuation.failed_launch(self.ctx,self.log)

    def test_wrong_supplement_pins_sessions_and_order_rejected(self):
        altered=copy.deepcopy(self.decision);altered['request']['maxAdditionalWorkerLaunches']=3
        with self.assertRaises(Rejection):continuation.prepare(continuation.REVIEW,self.ctx,self.log,
                                        self.commit,altered,digest(altered))
        with self.assertRaises(Rejection):continuation.prepare(continuation.ADJUDICATION,self.ctx,self.log,
                                        self.commit,self.decision,self.pin)
        review_stage=continuation.prepare(continuation.REVIEW,self.ctx,self.log,self.commit,self.decision,self.pin)
        proposal=self.fixture.proposal(review_stage,self.ctx['first']['proposal']['output'])
        item={'input':review_stage,'proposal':proposal,'receipt':None}
        parent=self.ctx['first']['receipt']['task']['observed']['sessionId']
        for reused in (continuation.FAILED_SESSION,self.ctx['first']['receipt']['worker']['observed']['sessionId']):
            with self.assertRaisesRegex(Rejection,'continuation-worker-budget-or-reuse'):
                continuation.capture(continuation.REVIEW,item,self.ctx,self.log,self.commit,self.decision,
                                     self.pin,sol_launch('codex-worker',reused,parent))
        forged=copy.deepcopy(self.ctx);forged['first']['ledger']['outcomes'][0]['status']='unresolved'
        with self.assertRaises(Rejection):continuation.request(forged,self.log,self.commit)

    def test_failure_proof_and_preview_are_fail_closed(self):
        preview=continuation.request(self.ctx,self.log,self.commit,preview=True)
        self.assertNotEqual(preview['schema'],continuation.REQUEST_SCHEMA)
        self.assertEqual(preview['codeCommit'],'PENDING_REVIEWED_COMMIT')
        unapprovable=copy.deepcopy(self.decision);unapprovable['request']=preview
        with self.assertRaises(Rejection):continuation.authorize(self.ctx,self.log,self.commit,
                                                unapprovable,digest(unapprovable))
        for kwargs in ({'error':'different failure'},{'model':'gpt-5.6-sol'},{'final':True}):
            self.write_log(**kwargs)
            with mock.patch.object(continuation,'FAILED_LOG_SHA',hashlib.sha256(self.log.read_bytes()).hexdigest()):
                with self.assertRaises(Rejection):continuation.request(self.ctx,self.log,self.commit)

    def test_final_removal_never_inherits_extraction_progress(self):
        review=self.review();adjudication=self.adjudication(review,remove=True)
        result=continuation.report(self.ctx,self.log,self.commit,self.decision,self.pin,review,adjudication)
        self.assertEqual(result['extractionGateStatus'],'partial_progress')
        self.assertEqual(result['finalKnownCoverageStatus'],'not_established')
        self.assertEqual(result['finalMaterialObligationIds'],[])
        changed=copy.deepcopy(adjudication);changed['ledger']['outcomes'][0]['status']='represented'
        with self.assertRaises(Rejection):continuation.report(self.ctx,self.log,self.commit,
                                              self.decision,self.pin,review,changed)

    def test_historical_and_current_code_checks_are_distinct(self):
        self.patchers[1].stop();self.patchers[2].stop()
        def current_drift(*args):
            if args==('rev-parse','HEAD'):return (self.commit+'\n').encode()
            path=args[1].split(':',1)[1]
            return b'drift' if path==continuation.CODE else (continuation.ROOT/path).read_bytes()
        with mock.patch.object(continuation.original.old,'git',side_effect=current_drift):
            with self.assertRaisesRegex(Rejection,'continuation-code-drift'):
                continuation.verify_current_code(self.commit)
        def historical_drift(*args):
            path=args[1].split(':',1)[1]
            return b'drift' if path==continuation.original.CODE else (continuation.ROOT/path).read_bytes()
        with mock.patch.object(continuation.original.old,'git',side_effect=historical_drift):
            with self.assertRaisesRegex(Rejection,'continuation-code-drift'):
                continuation.verify_historical_code()

    def test_repaired_historical_review_uses_only_remaining_adjudicator_slot(self):
        name=continuation.REVIEW
        stage=continuation.prepare(name,self.ctx,self.log,self.commit,self.decision,self.pin)
        proposal=self.fixture.proposal(stage,self.ctx['first']['proposal']['output'])
        continuation.original.old.write_new(self.workdir/'decision-request.json',self.req)
        continuation.original.old.write_new(self.workdir/'approved-decision.json',self.decision)
        continuation.original.old.write_new(self.workdir/(name+'.input.json'),stage)
        reserved=continuation.reserve_once(self.workdir,name,self.ctx,self.log,self.commit,self.decision,self.pin)
        worker_log=self.worker_log('synthetic-replacement-review',phase='final_answer')
        with mock.patch.object(continuation,'terminal_result',return_value=('unknown',None)):
            unknown=continuation.bind_once(self.workdir,name,worker_log,'synthetic-replacement-review',
                                           'turn',self.ctx,self.log,self.commit,self.decision,self.pin)
        continuation.original.old.write_new(self.workdir/(name+'.proposal.json'),proposal)
        unknown_bytes=(self.workdir/(name+'.attempt.json')).read_bytes()
        self.assertEqual(unknown['status'],'unknown')
        self.assertEqual(continuation.terminal_result(worker_log.read_bytes(),'turn'),('completed','final_answer'))

        def evidence(ctx,directory,path):
            self.assertEqual(directory,self.workdir)
            self.assertEqual(path,worker_log)
            self.assertEqual(continuation.terminal_result(path.read_bytes(),'turn'),('completed','final_answer'))
            self.assertEqual(digest(continuation.original.old.read(directory/(name+'.proposal.json'))),digest(proposal))
            return {'requestSha256':digest(self.req),'decisionSha256':self.pin,
                    'inputSha256':digest(stage),'reservationSha256':digest(reserved),
                    'originalUnknownAttemptSha256':digest(unknown),'proposalSha256':digest(proposal),
                    'logSha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'workerSessionId':'synthetic-replacement-review','workerTurnId':'turn',
                    'hostTerminalPhase':'final_answer','hostTerminalStatus':'completed',
                    'reclassifiedAttemptSha256':digest({**unknown,'status':'completed'})}

        def historical_git(command,object_name):
            self.assertEqual(command,'show')
            path=object_name.split(':',1)[1]
            return (continuation.ROOT/path).read_bytes()

        with (mock.patch.object(continuation,'review_correction_preview',side_effect=evidence),
              mock.patch.object(continuation,'REVIEW_CORRECTION_PINS',
                                {'request':digest(self.req),'decision':self.pin}),
              mock.patch.object(continuation.original.old,'git',side_effect=historical_git)):
            record=continuation.repair_document(self.ctx,self.log,self.commit,self.decision,self.pin)
            record['status']='reviewed'
            self.ctx['repair']=record;self.ctx['repairPin']=digest(record)
            review={'input':stage,'proposal':proposal,'reservation':reserved,'attempt':unknown,'receipt':None}
            review['receipt']=continuation.capture(name,review,self.ctx,self.log,self.commit,
                                                   self.decision,self.pin,unknown['worker'])
            self.assertEqual((self.workdir/(name+'.attempt.json')).read_bytes(),unknown_bytes)
            self.assertEqual(review['receipt']['originalUnknownAttemptSha256'],digest(unknown))
            self.assertEqual(review['receipt']['executionRepairSha256'],self.ctx['repairPin'])
            self.assertEqual(len(continuation.attempts(self.ctx,self.req,review)),3)
            with self.assertRaisesRegex(Rejection,'continuation-review-launch-already-consumed'):
                continuation.reserve_once(self.workdir,name,self.ctx,self.log,self.commit,
                                          self.decision,self.pin)
            changed=copy.deepcopy(review);changed['proposal']['output']={}
            with self.assertRaises(Rejection):
                continuation.validate_receipt(name,changed,self.ctx,self.log,self.commit,self.decision,self.pin)
            with self.assertRaises(Rejection):
                continuation.prepare(continuation.ADJUDICATION,self.ctx,self.log,'f'*40,
                                     self.decision,self.pin,review)
            with self.assertRaises(Rejection):
                continuation.prepare(continuation.ADJUDICATION,self.ctx,self.log,self.commit,
                                     {**self.decision,'approval':'rejected'},self.pin,review)
            adjudication=self.adjudication(review,remove=True)
            self.assertEqual(adjudication['reservation']['slotNumber'],4)
            result=continuation.report(self.ctx,self.log,self.commit,self.decision,self.pin,review,adjudication)
            self.assertEqual(result['finalKnownCoverageStatus'],'not_established')
            self.assertEqual(result['finalMaterialObligationIds'],[])
            self.assertEqual(result['launchAttempts'][2]['attemptSha256'],digest(unknown))
            self.assertEqual(result['launchAttempts'][3]['status'],'completed')


if __name__=='__main__':unittest.main()
