import copy
import unittest
from knowledge_export_v2_draft2_support import ROOT,k,runtime,uid,fixture,correction,reaffirmation,export,seal,bind_assessments,independent_correction


class KnowledgeExportDraft2Tests(unittest.TestCase):
    def setUp(self):self.base=fixture()

    def test_checked_in_positive_fixtures_are_exact(self):
        for label,data in [('initial',self.base),('source-correction',correction(self.base,True)),('extraction-correction',correction(self.base,False)),('reaffirmation',reaffirmation(self.base)),('independent-correction',independent_correction(self.base))]:
            with self.subTest(label=label):
                directory=ROOT/'tests/fixtures/knowledge-export-v2-draft2'/label
                for name,value in zip(('snapshot','inventory','profile','trust','receipts','knowledge-method-registry'),data):
                    self.assertEqual((directory/(name+'.json')).read_bytes(),k.canonical(value))
                self.assertEqual((directory/'batch.json').read_bytes(),k.canonical(export(data)))

    def test_both_corrections_preserve_every_prior_immutable_object(self):
        initial=export(self.base)
        for source_change in (False,True):
            data=correction(self.base,source_change);later=export(data)
            for kind in k.COLLECTIONS:
                for old in initial[kind]:self.assertIn(old,later[kind],kind)
            self.assertEqual(k.replay_identity([initial,later,later])['uniqueExports'],2)
            self.assertEqual(len(later['sourceRecords']),4 if source_change else 3)
            for key in ('requestedLogicalRecords','dependencyLogicalRecords','sourceUnits','entries','structuralUnits','expectedSpans','representedSpans','uncertainSpans','blockedSpans','extractionCompleteRecords'):
                self.assertEqual(later['coverage'][key],initial['coverage'][key],key)
            self.assertEqual(len(later['currentSpanDispositionSelection']),4)
            self.assertEqual(len(later['spanDispositions']),8)
            self.assertEqual(len(later['entities']),6)
            self.assertEqual({e['logicalEntityId'] for e in later['entities']},{e['logicalEntityId'] for e in initial['entities']})

    def test_reaffirmation_keeps_source_and_dispositions_byte_identical(self):
        initial=export(self.base);later=export(reaffirmation(self.base))
        for key in ('sourceRecords','spanDispositions','currentSourceSelection','currentSpanDispositionSelection','claims'):
            self.assertEqual(later[key],initial[key])
        self.assertEqual(len(later['assessments']),len(initial['assessments'])+3)
        self.assertEqual(k.replay_identity([initial,later])['uniqueExports'],2)

    def test_old_ids_cannot_be_rewritten_after_replay(self):
        initial=export(self.base);later=export(correction(self.base,False))
        later['spanDispositions'][0]['reasonCode']='pending'
        later['payloadSha256']=k.digest({a:v for a,v in later.items() if a!='payloadSha256'})
        with self.assertRaisesRegex(k.Rejection,'immutable-id-conflict'):k.replay_identity([initial,later])

    def test_current_selection_cannot_revive_retired_source_or_claims(self):
        data=list(correction(self.base,True));s,i,p,_,b,_=data
        s['currentSourceSelection']=copy.deepcopy(self.base[0]['currentSourceSelection'])
        s['currentSpanDispositionSelection']=copy.deepcopy(self.base[0]['currentSpanDispositionSelection'])
        s['assessmentSelection']=copy.deepcopy(self.base[0]['assessmentSelection'])
        data[3]=seal(s,i,p,b)
        with self.assertRaises(k.Rejection):export(data)

    def test_current_projection_cannot_be_replaced_by_old_receipt_chain(self):
        data=list(correction(self.base,False));s,i,p,_,b,_=data
        old=k.indexed(self.base[0]['assessments'])
        current=k.indexed(s['assessments'])
        for selection,prior in zip(s['assessmentSelection'],self.base[0]['assessmentSelection']):
            current[selection['extractionAssessmentId']]['receiptArtifactIds']=old[prior['extractionAssessmentId']]['receiptArtifactIds']
        data[3]=seal(s,i,p,b)
        with self.assertRaisesRegex(k.Rejection,'knowledge-current-output-mismatch'):export(data)

    def test_source_and_disposition_inputs_must_both_be_bound(self):
        for kind in ('sourceRecords','spanDispositions'):
            data=list(copy.deepcopy(self.base));s,i,p,_,b,_=data
            assessment=next(a for a in s['assessments'] if a['kind']=='extraction')
            assessment['targets']=[r for r in assessment['targets'] if r['kind']!=kind]
            assessment['inputs']=[r for r in assessment['inputs'] if r['ref']['kind']!=kind]
            data[3]=seal(s,i,p,b)
            with self.assertRaisesRegex(k.Rejection,'assessment-binding-mismatch'):export(data)

    def test_host_runtime_details_never_cross_consumer_boundary(self):
        payload=export(self.base);text=k.canonical(payload).decode('utf-8')
        for field in ('sessionId','turnId','reasoning','model','worker','request','observed'):
            self.assertNotIn('"'+field+'":',text)
        self.assertTrue(any(a['kind']=='knowledge_receipt' for a in payload['artifacts']))
        self.assertEqual(len(payload['names']),2)
        self.assertEqual(payload['values'][0]['amountNumerator'],2)
        self.assertEqual(payload['values'][0]['amountDenominator'],1)

    def test_stage_receipts_pin_actual_synthetic_host_metadata(self):
        bundle=self.base[4];registry=self.base[5]
        self.assertEqual(len(runtime.validate_bundle(bundle,registry,k.digest(bundle))),6)
        for owner in ('task','worker'):
            for field,value in [('provider','unknown'),('model','unknown'),('reasoning','high')]:
                changed=copy.deepcopy(bundle);changed['receipts'][0][owner]['observed'][field]=value
                with self.assertRaisesRegex(k.Rejection,'knowledge-host-mismatch'):
                    runtime.validate_bundle(changed,registry,k.digest(changed))

    def test_receipt_stage_inputs_outputs_and_host_checkpoint_are_immutable(self):
        for mutate in [lambda b:b['bindings'][0]['inputs'].update(inventorySha256='0'*64),
                       lambda b:b['bindings'][2]['outputs']['objects'].pop(),
                       lambda b:b['receipts'][0]['worker']['observed'].update(turnId='wrong-turn'),
                       lambda b:b['receipts'][1].update(upstreamReceiptIds=[])]:
            changed=copy.deepcopy(self.base[4]);mutate(changed)
            for receipt in changed['receipts']:
                receipt['receiptSha256']=k.digest({a:v for a,v in receipt.items() if a!='receiptSha256'})
            with self.assertRaisesRegex(k.Rejection,'knowledge-receipt-binding-mismatch'):
                runtime.validate_bundle(changed,self.base[5],k.digest(changed))

    def test_fresh_independent_workers_required(self):
        for field,value in [('firstTurn',False),('forked',True)]:
            changed=copy.deepcopy(self.base[4]);changed['receipts'][1]['worker']['observed'][field]=value
            with self.assertRaisesRegex(k.Rejection,'knowledge-host-mismatch'):runtime.validate_bundle(changed,self.base[5],k.digest(changed))
        changed=copy.deepcopy(self.base[4]);receipt=changed['receipts'][1]
        receipt['worker']=copy.deepcopy(changed['receipts'][0]['worker'])
        receipt['checkpointSha256']=runtime.checkpoint(receipt)
        receipt['receiptSha256']=k.digest({a:v for a,v in receipt.items() if a!='receiptSha256'})
        with self.assertRaisesRegex(k.Rejection,'knowledge-independence-mismatch'):runtime.validate_bundle(changed,self.base[5],k.digest(changed))

    def test_real_receipts_and_registry_drift_are_disabled(self):
        changed=copy.deepcopy(self.base[4]);changed['receipts'][0]['fixtureClass']='not-a-fixture'
        with self.assertRaisesRegex(k.Rejection,'real-method-disabled'):runtime.validate_bundle(changed,self.base[5],k.digest(changed))
        registry=copy.deepcopy(self.base[5]);registry['methods'][0]['configuration']['reasoning']='ultra'
        with self.assertRaisesRegex(k.Rejection,'knowledge-registry-mismatch'):runtime.validate_bundle(self.base[4],registry,k.digest(self.base[4]))

    def test_independent_cohort_correction_retains_actual_receipt_bytes(self):
        later=independent_correction(self.base);export(later)
        old_receipts={r['id']:k.canonical(r) for r in self.base[4]['receipts']}
        new_receipts={r['id']:k.canonical(r) for r in later[4]['receipts']}
        for identity,content in old_receipts.items():self.assertEqual(new_receipts[identity],content)
        self.assertEqual(len(new_receipts),len(old_receipts)+3)
        for rid in (uid('sourceRecords',1),uid('sourceRecords',3)):
            old=next(x for x in self.base[0]['assessmentSelection'] if x['sourceRecordVersionId']==rid)
            new=next(x for x in later[0]['assessmentSelection'] if x['sourceRecordVersionId']==rid)
            self.assertEqual(old,new)
            self.assertEqual(k.indexed(self.base[0]['assessments'])[old['extractionAssessmentId']],k.indexed(later[0]['assessments'])[new['extractionAssessmentId']])
        self.assertEqual(k.replay_identity([export(self.base),export(later)])['uniqueExports'],2)

    def test_declared_dependency_must_match_actual_reference_closure(self):
        s=self.base[0]
        projection=k.semantic_projection(s,[uid('sourceRecords',1)],[uid('sourceRecords',3)])
        self.assertTrue(any(x['ref']=={'kind':'sourceRecords','id':uid('sourceRecords',3)} for x in projection['objects']))
        for deps in ([],[uid('sourceRecords',2),uid('sourceRecords',3)]):
            with self.assertRaisesRegex(k.Rejection,'knowledge-output-scope-mismatch'):
                k.semantic_projection(s,[uid('sourceRecords',1)],deps)

    def test_fully_resealed_foreign_or_omitted_semantics_still_rejected(self):
        for foreign in (False,True):
            data=list(copy.deepcopy(self.base));s,i,p,_,b,_=data
            binding=b['bindings'][-1];receipt=b['receipts'][-1]
            if foreign:
                entity=s['entities'][0]
                binding['outputs']['objects'].append({'ref':{'kind':'entities','id':entity['id']},'sha256':k.digest(entity)})
            else:binding['outputs']['objects'].pop()
            receipt['outputSha256']=k.digest(binding['outputs'])
            receipt['checkpointSha256']=runtime.checkpoint(receipt)
            receipt['receiptSha256']=k.digest({a:v for a,v in receipt.items() if a!='receiptSha256'})
            next(x for x in s['artifacts'] if x['id']==receipt['id'])['sha256']=k.digest(receipt)
            data[3]=seal(s,i,p,b)
            code='knowledge-output-scope-mismatch' if foreign else 'knowledge-current-output-mismatch'
            with self.assertRaisesRegex(k.Rejection,code):export(data)

    def test_not_started_metadata_does_not_claim_semantic_completion(self):
        data=list(copy.deepcopy(self.base));s,i,p,_,b,_=data
        selection=next(x for x in s['assessmentSelection'] if x['sourceRecordVersionId']==uid('sourceRecords',2))
        assessment=k.indexed(s['assessments'])[selection['extractionAssessmentId']]
        assessment['status']='not_started';assessment['receiptArtifactIds']=[]
        row=next(x for x in s['spanDispositions'] if x['sourceRecordVersionId']==uid('sourceRecords',2))
        row.update(status='unprocessed',reasonCode='pending')
        # This test changes the authored initial state before any export, not history.
        keep={r['id'] for r in b['receipts'] if uid('sourceRecords',2) not in r['sourceRecordVersionIds']}
        b['receipts']=[r for r in b['receipts'] if r['id'] in keep]
        b['bindings']=[r for r in b['bindings'] if r['receiptId'] in keep]
        s['artifacts']=[r for r in s['artifacts'] if r['kind']!='knowledge_receipt' or r['id'] in keep]
        bind_assessments(s);data[3]=seal(s,i,p,b)
        output=export(data)
        self.assertFalse(output['coverage']['scopeExtractionComplete'])
        self.assertEqual(output['coverage']['blockedSpans'],1)
        self.assertEqual(output['coverage']['extractionCompleteRecords'],1)

    def test_real_pilot_metadata_reproducible_and_unexecuted(self):
        import prepare_knowledge_pilot as pilot
        value=pilot.build()
        self.assertEqual(pilot.OUTPUT.read_bytes(),k.canonical(value))
        self.assertEqual(value['counts'],{'entries':13,'structuralUnits':7,'substantiveUnits':20,'retainedFindings':4})
        self.assertEqual(value['knowledgeExtractionStatus'],'not_started')
        self.assertFalse(value['realExecutionEnabled'])
        self.assertEqual(value['ownerDecisionStatus'],'not_recorded')


    def test_shared_draft2_adversarial_cases_with_fresh_pins(self):
        suite=k.read(ROOT/'tests/fixtures/knowledge-export-v2-draft2/adversarial-cases.json')
        for case in suite['cases']:
            with self.subTest(case=case['id']):
                data=list(copy.deepcopy(self.base));s,i,p,_,b,_=data
                inputs={'snapshot':s,'inventory':i,'profile':p}
                for patch in case['patches']:
                    target=inputs[patch['input']]
                    for part in patch['path'][:-1]:target=target[part]
                    key=patch['path'][-1]
                    if patch['op']=='append':target[key].append(copy.deepcopy(patch['value']))
                    else:target[key]=copy.deepcopy(patch['value'])
                data[3]=seal(s,i,p,b)
                with self.assertRaisesRegex(k.Rejection,'^'+case['expectedCode']+'$'):export(data)


if __name__=='__main__':unittest.main()
