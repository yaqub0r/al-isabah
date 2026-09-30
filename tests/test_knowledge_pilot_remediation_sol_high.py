"""Synthetic rehearsal of the separately pinned Sol/High remediation path."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_knowledge_pilot_remediation import baseline_fixture,proposal
import knowledge_pilot_remediation as historical
import knowledge_pilot_remediation_sol_high as sol
from knowledge_export import digest,Rejection


def launch(kind,session,parent=None,model='gpt-6-sol',reasoning='high'):
    observed={'source':'codex-session-metadata','sessionId':session,'turnId':'turn-1',
              'provider':'openai','model':model,'reasoning':reasoning,'firstTurn':True,'forked':False}
    if kind=='codex-worker':observed['parentSessionId']=parent
    return {'request':sol.old.host_runtime.launch_request(kind,model,reasoning),'observed':observed}


class SolHighRemediationTests(unittest.TestCase):
    def setUp(self):
        self.packet,self.partition,self.baseline,unused=baseline_fixture()
        self.request=sol.request(self.packet,self.partition,'0'*40,self.baseline)
        self.decision={'schema':sol.DECISION_SCHEMA,'request':copy.deepcopy(self.request),
                       'approval':'approved','origin':{'kind':'actual_user_message',
                       'threadId':sol.old.COORDINATOR,'userTurnReference':'synthetic-only',
                       'recordedBy':'trusted_coordinator'}}
        self.pin=digest(self.decision)

    def test_new_request_is_exactly_sol_high_and_old_request_is_unchanged(self):
        registry,config=sol.configuration()
        self.assertEqual((config['model'],config['reasoning']),('gpt-6-sol','high'))
        self.assertEqual(self.request['methodRegistrySha256'],digest(registry))
        self.assertEqual(self.request['taskRequest'],launch('codex-task','task')['request'])
        self.assertEqual(self.request['workerRequest'],launch('codex-worker','worker','task')['request'])
        old_request=historical.request(self.packet,self.partition,'0'*40,self.baseline)
        self.assertEqual(old_request['taskRequest']['overrides']['model'],'gpt-5.6-sol')
        self.assertEqual(old_request['workerRequest']['overrides']['reasoning_effort'],'xhigh')
        with self.assertRaisesRegex(Rejection,'remediation-new-decision-required'):
            historical.authorize(self.decision,self.pin,self.packet,self.partition,'0'*40,self.baseline)

    def test_three_fresh_sequential_workers_and_actual_host_settings(self):
        stages=[];task=launch('codex-task','synthetic-new-task')
        for n,name in enumerate(sol.old.STAGES):
            stage=sol.prepare(name,self.decision,self.pin,self.packet,self.partition,'0'*40,self.baseline,stages)
            value=proposal(stage,self.packet)
            worker=launch('codex-worker','synthetic-new-worker-'+str(n),task['observed']['sessionId'])
            receipt=sol.capture(stage,value,self.packet,self.pin,task,worker,[x['receipt'] for x in stages])
            stages.append({'input':stage,'proposal':value,'receipt':receipt})
        result=sol.report(self.decision,self.pin,self.packet,self.partition,'0'*40,self.baseline,stages)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['stageReceiptSha256'],[x['receipt']['receiptSha256'] for x in stages])
        changed=copy.deepcopy(stages[2]['receipt'])
        changed['worker']['observed']['model']='gpt-5.6-sol'
        with self.assertRaisesRegex(Rejection,'trial-host-mismatch'):
            sol.validate_receipt(changed,stages[2]['input'],stages[2]['proposal'],self.pin,
                                 [x['receipt'] for x in stages[:2]])
        with self.assertRaisesRegex(Rejection,'remediation-historical-worker-reuse'):
            sol.capture(stages[0]['input'],stages[0]['proposal'],self.packet,self.pin,task,
                        launch('codex-worker',self.baseline['stages'][0]['receipt']['worker']['observed']['sessionId'],
                               task['observed']['sessionId']),[])

    def test_exact_decision_and_scope_required(self):
        changed=copy.deepcopy(self.decision);changed['request']['maxFreshWorkers']=4
        with self.assertRaisesRegex(Rejection,'trial-decision-scope-mismatch'):
            sol.authorize(changed,digest(changed),self.packet,self.partition,'0'*40,self.baseline)
        changed=copy.deepcopy(self.decision);changed['origin']['kind']='agent_message'
        with self.assertRaisesRegex(Rejection,'trial-user-authorization-required'):
            sol.authorize(changed,digest(changed),self.packet,self.partition,'0'*40,self.baseline)
        changed=copy.deepcopy(self.decision);changed['request']['workerRequest']['overrides']['reasoning_effort']='xhigh'
        with self.assertRaisesRegex(Rejection,'trial-decision-scope-mismatch'):
            sol.authorize(changed,digest(changed),self.packet,self.partition,'0'*40,self.baseline)


if __name__=='__main__':unittest.main()
