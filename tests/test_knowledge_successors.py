"""Synthetic explicit-patch planning: no model, approval, or source modification."""
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from knowledge_export_v2_draft3_support import capabilities,helper_input,helper_correction,export,k,uid,ROOT
import knowledge_successors as helper


class KnowledgeSuccessorTests(unittest.TestCase):
    def setUp(self):
        self.data=capabilities();self.source=helper_input(self.data[0]);self.pin=k.digest(self.source)
        old=next(x['value'] for x in self.source['objects'] if x['kind']=='qualifications' and x['value']['id']==uid('qualifications','pledged-quantity'))
        new=copy.deepcopy(old);new['criticalStatus']='disputed'
        self.patch={'ref':{'kind':'qualifications','id':old['id']},'beforeSha256':k.digest(old),'replacement':new}
    def plan(self,patches=None):return helper.plan(self.source,self.pin,patches or [self.patch],uid('successor','test'))
    def test_cycle_safe_rewiring_is_deterministic_and_preserves_input(self):
        before=k.canonical(self.source);result=self.plan()
        self.assertEqual(result,self.plan());self.assertEqual(k.canonical(self.source),before)
        self.assertGreater(len(result['replacements']),1)
        self.assertTrue(any(x['from']['kind']=='reports' for x in result['replacements']))
        self.assertTrue(any(x['from']['kind']=='claims' for x in result['replacements']))
        self.assertFalse(result['semanticApprovalCreated']);self.assertFalse(result['receiptCreated'])
        old={(x['kind'],x['value']['id']):x['value'] for x in self.source['objects']}
        affected={(x['from']['kind'],x['from']['id']) for x in result['replacements']}
        current={(x['kind'],x['value']['id']):x['value'] for x in result['candidate']['objects']}
        for key in old.keys()-affected:self.assertEqual(old[key],current[key])
        for row in result['replacements']:
            self.assertEqual(row['beforeSha256'],k.digest(old[(row['from']['kind'],row['from']['id'])]))
            self.assertFalse(helper.references(row['value'])&affected)
    def test_noop_preserves_every_object_and_creates_no_versions(self):
        patch=copy.deepcopy(self.patch);patch['replacement']=next(x['value'] for x in self.source['objects'] if x['value']['id']==patch['ref']['id'])
        result=self.plan([patch]);self.assertEqual(result['replacements'],[])
        self.assertEqual({k.digest(x) for x in result['candidate']['objects']},{k.digest(x) for x in self.source['objects']})
    def test_only_typed_references_are_rewritten(self):
        value={'rationale':'old','logicalEntityId':'old','subjectRef':{'kind':'entities','id':'old'},'entityIds':['old'],'transmission':[{'entityIds':['old'],'position':0}]}
        changed=helper.rewire(value,{('entities','old'):'new'})
        self.assertEqual(changed['rationale'],'old');self.assertEqual(changed['logicalEntityId'],'old')
        self.assertEqual(changed['subjectRef']['id'],'new');self.assertEqual(changed['transmission'][0]['position'],0)
    def test_stale_base_seed_hash_and_unknown_reference_rejected(self):
        with self.assertRaisesRegex(k.Rejection,'successor-base-drift'):helper.plan(self.source,'0'*64,[self.patch],uid('successor','x'))
        patch=copy.deepcopy(self.patch);patch['beforeSha256']='0'*64
        with self.assertRaisesRegex(k.Rejection,'successor-base-drift'):self.plan([patch])
        patch=copy.deepcopy(self.patch);patch['replacement']['targets']=[{'kind':'claims','id':uid('claims','missing')}]
        with self.assertRaisesRegex(k.Rejection,'missing-reference'):self.plan([patch])
    def test_duplicate_seed_and_implicit_logical_identity_change_rejected(self):
        with self.assertRaisesRegex(k.Rejection,'successor-patch-shape'):self.plan([self.patch,self.patch])
        old=next(x['value'] for x in self.source['objects'] if x['kind']=='entities');new=copy.deepcopy(old);new['logicalEntityId']=uid('logical','invented')
        with self.assertRaisesRegex(k.Rejection,'successor-logical-identity-change'):self.plan([{'ref':{'kind':'entities','id':old['id']},'beforeSha256':k.digest(old),'replacement':new}])
    def test_helper_correction_preserves_history_receipts_and_other_cohort(self):
        before=export(self.data);data=helper_correction(self.data);after=export(data)
        self.assertEqual(k.replay_identity([before,after,after])['uniqueExports'],2)
        for kind in k.COLLECTIONS:
            for old in self.data[0][kind]:self.assertIn(old,data[0][kind],kind)
        for old in self.data[4]['receipts']:self.assertIn(old,data[4]['receipts'])
        for old in self.data[4]['bindings']:self.assertIn(old,data[4]['bindings'])
        rid=uid('sourceRecords',2)
        self.assertEqual(next(x for x in self.data[0]['assessmentSelection'] if x['sourceRecordVersionId']==rid),next(x for x in data[0]['assessmentSelection'] if x['sourceRecordVersionId']==rid))
        directory=ROOT/'tests/fixtures/knowledge-export-v2-draft3/helper-correction'
        self.assertEqual((directory/'batch.json').read_bytes(),k.canonical(after))
    def test_one_sided_edits_reject_without_inventing_the_matching_edit(self):
        cases=[('reports',1,'claimIds'),('entities',1,'mentionIds'),('entities',1,'nameIds'),('claims','pledged-quantity','qualificationIds'),('ambiguityGroups',1,'members')]
        for kind,identity,field in cases:
            old=next(x['value'] for x in self.source['objects'] if x['kind']==kind and x['value']['id']==uid(kind,identity))
            changed=copy.deepcopy(old);changed[field]=changed[field][1:]
            patch={'ref':{'kind':kind,'id':old['id']},'beforeSha256':k.digest(old),'replacement':changed}
            with self.subTest(kind=kind),self.assertRaises(k.Rejection):self.plan([patch])
    def test_explicit_two_sided_patch_is_allowed_and_cycle_safe(self):
        claim=next(x['value'] for x in self.source['objects'] if x['kind']=='claims' and x['value']['id']==uid('claims','nursing-sibling-of'))
        report=next(x['value'] for x in self.source['objects'] if x['kind']=='reports' and x['value']['id']==uid('reports','additional-route'))
        new_claim=copy.deepcopy(claim);new_claim['reportIds'].append(report['id'])
        new_report=copy.deepcopy(report);new_report['claimIds'].append(claim['id'])
        patches=[{'ref':{'kind':kind,'id':old['id']},'beforeSha256':k.digest(old),'replacement':new} for kind,old,new in [('claims',claim,new_claim),('reports',report,new_report)]]
        with self.assertRaisesRegex(k.Rejection,'successor-reciprocal-mismatch'):self.plan(patches[:1])
        result=self.plan(patches)
        self.assertEqual(result,self.plan(list(reversed(patches))))
        helper.reciprocal_consistency({(x['kind'],x['value']['id']):x['value'] for x in result['candidate']['objects']})

    def test_cli_defaults_dry_run_and_only_creates_new_private_output(self):
        runtime=ROOT/'.runtime';runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime,prefix='synthetic-successor-') as directory:
            root=Path(directory);source=root/'input.json';patches=root/'patches.json';output=root/'plan.json'
            source.write_bytes(k.canonical(self.source));patches.write_bytes(k.canonical([self.patch]))
            command=[sys.executable,str(ROOT/'scripts/knowledge_successors.py'),'--input',str(source),'--base-sha256',self.pin,'--patches',str(patches),'--namespace',uid('successor','cli')]
            run=lambda *extra:subprocess.run(command+list(extra),capture_output=True,text=True)
            self.assertEqual(run().returncode,0);self.assertFalse(output.exists())
            self.assertNotEqual(run('--output',str(output)).returncode,0)
            self.assertEqual(run('--apply','--output',str(output)).returncode,0)
            before=output.read_bytes();self.assertNotEqual(run('--apply','--output',str(output)).returncode,0)
            self.assertEqual(output.read_bytes(),before);self.assertEqual(source.read_bytes(),k.canonical(self.source))
            self.assertNotEqual(run('--apply','--output',str(ROOT/'not-a-private-plan.json')).returncode,0)


if __name__=='__main__':unittest.main()
