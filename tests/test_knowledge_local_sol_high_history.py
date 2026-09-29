"""Real-shaped synthetic Sol/High history, with no actual source or approval."""
import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from knowledge_local_support import history_fixture,rich_output
from test_knowledge_pilot_trial import launch
import knowledge_local_execution as execution
import knowledge_local_projection as projection
import knowledge_pilot_remediation as remediation
import knowledge_pilot_remediation_sol_high as sol_high
from knowledge_export import digest,Rejection


def sol_launch(kind,session,parent='synthetic-sol-task'):
    value=launch(kind,session,parent)
    value['request']=sol_high.old.host_runtime.launch_request(kind,'gpt-6-sol','high')
    value['observed'].update(model='gpt-6-sol',reasoning='high')
    return value


def sol_history():
    historical=history_fixture()
    baseline=historical['baseline'];partition=historical['partition']
    packet=historical['stages'][0]['input']['lockedInput']
    request=execution.expected_request(packet,partition,baseline,execution.SOL_HIGH_COMMIT)
    decision={'schema':sol_high.DECISION_SCHEMA,'request':request,'approval':'approved',
              'origin':{'kind':'actual_user_message','threadId':sol_high.old.COORDINATOR,
                        'userTurnReference':'SYNTHETIC-CONFORMANCE-ONLY','recordedBy':'trusted_coordinator'}}
    stages=[];task=sol_launch('codex-task','synthetic-sol-task')
    for n,name in enumerate(sol_high.old.STAGES):
        stage=execution.expected_input(name,request,digest(decision),packet,partition,baseline,stages)
        output=rich_output(stage,packet)
        proposal={'schema':'al-isabah.knowledge-remediation-proposal.v1','output':output,
                  'baselineSha256':digest(baseline),'objectSuccessors':[],
                  'concernOutcomes':[{'baselineConcernId':c['id'],'baselineConcernSha256':digest(c),
                       'outcome':'resolved' if output['concerns'][i]['status']=='resolved' else 'residual',
                       'rationale':'Synthetic conformance outcome only.'}
                       for i,c in enumerate(remediation.baseline_output(baseline)['concerns'])]}
        receipt=sol_high.capture(stage,proposal,packet,digest(decision),task,
                  sol_launch('codex-worker','synthetic-sol-worker-'+str(n)),
                  [x['receipt'] for x in stages])
        stages.append({'input':stage,'proposal':proposal,'receipt':receipt})
    return {'schema':execution.HISTORY_SCHEMA,'decision':decision,'partition':partition,
            'baseline':baseline,'stages':stages,
            'report':execution.expected_report(decision,packet,partition,baseline,stages)}


class SolHighHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.new=sol_history();cls.old=history_fixture()

    def test_both_exact_historical_methods_replay_without_current_head(self):
        with mock.patch.object(sol_high.old,'git',return_value=b'f'*40+b'\n'):
            self.assertEqual(execution.validate_history(self.old)['packetSha256'],
                             execution.validate_history(self.new)['packetSha256'])
        request=self.new['decision']['request']
        self.assertEqual(request['codeCommit'],execution.SOL_HIGH_COMMIT)
        self.assertEqual(request['methodRegistrySha256'],execution.SOL_HIGH_METHOD_SHA256)
        self.assertEqual(request['taskRequest'],sol_high.old.host_runtime.launch_request('codex-task','gpt-6-sol','high'))
        self.assertEqual(request['workerRequest'],sol_high.old.host_runtime.launch_request('codex-worker','gpt-6-sol','high'))
        self.assertEqual(self.old['decision']['request']['codeCommit'],execution.EXECUTION_COMMIT)

    def test_sol_high_projection_preserves_partial_and_actual_source_ids(self):
        packet=execution.validate_history(self.new)
        requested=sorted(r['id'] for r in packet['records'])
        snapshot,inventory,profile,bundle=projection.project_history(self.new,requested)
        self.assertEqual(bundle['history'],self.new)
        self.assertEqual({r['id'] for r in snapshot['sourceRecords']},set(requested))
        self.assertEqual(snapshot['admissionClass'],'local_provisional')
        self.assertTrue(any(r['status']=='partial' for r in bundle['completionDerivation']))

    def test_new_decision_and_host_observations_are_not_downgradable(self):
        for change in (
            lambda h:h['decision'].update(schema='al-isabah.knowledge-remediation-decision.v1'),
            lambda h:h['decision']['request'].update(codeCommit=execution.EXECUTION_COMMIT),
            lambda h:h['decision']['request']['workerRequest']['overrides'].update(reasoning_effort='xhigh'),
            lambda h:h['stages'][1]['receipt']['worker']['observed'].update(model='gpt-5.6-sol'),
            lambda h:h['stages'][1]['receipt']['worker']['observed'].update(reasoning='xhigh'),
            lambda h:h['stages'][1]['receipt']['worker']['observed'].update(parentSessionId='other-parent'),
            lambda h:h['stages'][1]['receipt'].update(upstreamReceiptSha256=[]),
            lambda h:h['stages'][2]['receipt']['worker']['observed'].update(sessionId=h['stages'][0]['receipt']['worker']['observed']['sessionId']),
        ):
            value=copy.deepcopy(self.new);change(value)
            with self.assertRaises(Rejection):execution.validate_history(value)

    def test_only_exact_sol_high_adapter_and_method_bytes_are_accepted(self):
        original=Path.read_bytes
        for target in (sol_high.ROOT/sol_high.CODE,sol_high.METHOD):
            def changed(path):return b'changed historical method' if path==target else original(path)
            with mock.patch.object(Path,'read_bytes',changed):
                with self.assertRaisesRegex(Rejection,'local-sol-high-verifier-drift'):
                    execution.validate_history(self.new)
        execution.validate_history(self.old)


if __name__=='__main__':unittest.main()
