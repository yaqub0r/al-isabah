"""Local real-shaped conformance with explicitly authored synthetic authority only."""
import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from knowledge_local_support import artifact_fixture,packet_fixture,rich_output
import knowledge_local_execution as execution
import knowledge_local_projection as projection
import knowledge_local_authorization as authorization
import knowledge_export_local as local
import knowledge_local_schema as schemas
import knowledge_pilot_validation_v2 as private
import knowledge_pilot_trial as old
from knowledge_export import canonical,digest,read,Rejection


class KnowledgeLocalExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial=artifact_fixture();cls.correction=artifact_fixture('correction',True)
    def sample(self):return copy.deepcopy(self.initial)
    def seal_authorization(self,f):
        f['trust']['upstreamAuthorizationSha256']=authorization.authorization_digest(f['authorization'])
    def repin(self,f,raw=None):
        f['snapshot']['receiptBundleSha256']=digest(f['receipts'])
        f['export']=local.payload_value(f['snapshot'],f['inventory'])
        f['trust']=local.bindings_value(f['snapshot'],f['inventory'],f['profile'],f['receipts'],f['export'],raw)
        f['authorization']['subjectSha256']=authorization.subject(f['trust']);self.seal_authorization(f)
    def verify(self,f,**kwargs):
        args={'expected_pin':f['trust']['upstreamAuthorizationSha256'],'authority_id':'synthetic-conformance-owner',
              'as_of':'2026-01-02T00:00:00Z','revoked':[],'requested_use':'local_noncommercial_reading','raw_export':canonical(f['export'])}
        args.update(kwargs)
        return local.verify(f['snapshot'],f['inventory'],f['profile'],f['receipts'],f['export'],f['trust'],f['authorization'],**args)
    def test_real_shaped_initial_correction_replay_and_restore(self):
        for f in (self.initial,self.correction):
            result=self.verify(f);self.assertEqual(result['status'],'authorized_local_provisional');self.assertFalse(result['consumerAdmissionAuthorized'])
            self.assertFalse(result['publicReleaseAuthorized']);self.assertFalse(f['export']['coverage']['scopeExtractionComplete'])
            self.assertEqual({r['derivedBy'] for r in f['receipts']['receipts']},{'exporter'})
            self.assertIn(len(f['receipts']['receipts']),(3,6));self.assertTrue(f['export']['lifecycleEvents'])
        replay=local.replay_identity([self.initial['export'],self.correction['export'],self.initial['export']])
        self.assertEqual(replay['uniqueExports'],2)
    def test_correction_carries_prior_retirement_bytes_and_retires_only_live_predecessors(self):
        first=self.initial['export'];second=self.correction['export']
        old_events={e['id']:e for e in first['lifecycleEvents']};new_events={e['id']:e for e in second['lifecycleEvents']}
        self.assertTrue(old_events.keys()<=new_events.keys())
        for identity,event in old_events.items():self.assertEqual(event,new_events[identity])
        retired={(r['kind'],r['id']) for e in old_events.values() for r in e['targets']}
        for event in new_events.values():
            if event['id'] in old_events:continue
            targets={(r['kind'],r['id']) for r in event['targets']}
            self.assertFalse(targets&retired,event['id']);retired|=targets
        for kind in local.graph.COLLECTIONS:
            before={x['id']:x for x in first[kind]};after={x['id']:x for x in second[kind]}
            self.assertTrue(before.keys()<=after.keys(),kind)
            for identity,value in before.items():self.assertEqual(value,after[identity])

    def test_exact_metadata_overlay_and_semantic_code_identity(self):
        schemas.check_semantic_identity(read(schemas.SCHEMA));base=read(schemas.BASE);current=read(schemas.SCHEMA)
        for name,value in base['$defs'].items():
            if name not in schemas.MODIFIED_DEFS:self.assertEqual(value,current['$defs'][name],name)
        frozen=(old.ROOT/'scripts/knowledge_export_v2_draft3.py').read_text(encoding='utf-8')
        copied=(old.ROOT/'scripts/knowledge_local_semantics.py').read_text(encoding='utf-8')
        original=next(x for x in ast.parse(frozen).body if isinstance(x,ast.FunctionDef) and x.name=='validate_snapshot')
        new=next(x for x in ast.parse(copied).body if isinstance(x,ast.FunctionDef) and x.name=='validate_semantics')
        tail=original.body[-len(new.body):]
        changes=[n for n,(a,b) in enumerate(zip(tail,new.body)) if ast.dump(a)!=ast.dump(b)]
        self.assertEqual(len(changes),1);self.assertIn('synthetic_only',ast.unparse(tail[changes[0]]));self.assertIn('proposed',ast.unparse(new.body[changes[0]]))
    def test_historical_verifier_accepts_other_head_but_not_dependency_drift(self):
        with mock.patch.object(old,'git',return_value=b'f'*40+b'\n'):
            execution.validate_history(self.initial['receipts']['history'])
        original=Path.read_bytes;target=old.ROOT/'scripts/knowledge_pilot_remediation.py'
        def changed(path):return b'changed historical dependency' if path==target else original(path)
        with mock.patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(Rejection,'local-historical-verifier-drift'):execution.verify_historical_dependencies()
    def test_source_record_identity_excludes_editorial_fields(self):
        packet,_=packet_fixture();profile=projection.profile_value();requested=sorted(r['id'] for r in packet['records'])
        before=projection.inventory_value(packet,profile,requested)[1]
        changed=copy.deepcopy(packet);changed['records'][0].update(candidateEnglish={'title':'Changed editorial title'},candidateRecordSha256='f'*64,
            priorMachineAssessment='changed',retainedFindings=[{'category':'changed editorial evidence'}])
        self.assertEqual(before,projection.inventory_value(changed,profile,requested)[1])
        changed=copy.deepcopy(packet);changed['units'][0]['rawSha256']='f'*64
        after=projection.inventory_value(changed,profile,requested)[1]
        self.assertEqual(before[0]['id'],after[0]['id']);self.assertNotEqual(before[0]['recordSha256'],after[0]['recordSha256'])
        payload=copy.deepcopy(self.initial['export']);payload['sourceRecords'][0]['recordSha256']='f'*64
        payload['payloadSha256']=digest({k:v for k,v in payload.items() if k!='payloadSha256'})
        with self.assertRaisesRegex(Rejection,'immutable-id-conflict'):local.replay_identity([self.initial['export'],payload])
    def test_open_substantive_concern_does_not_become_complete_or_block_other_record(self):
        h=copy.deepcopy(self.initial['receipts']['history']);item=h['stages'][0];packet=item['input']['lockedInput'];output=item['proposal']['output']
        represented=[n for n,r in enumerate(output['spanDispositions']) if r['status'] in {'represented','represented_uncertain'}]
        affected,clean=represented[:2]
        output['concerns'][affected]['status']='open';output['retainedFindingCoverage'][affected]['status']='retained'
        private.validate_output(output,item['input'],packet)
        snapshot=projection.stage_snapshot(item,packet,self.initial['inventory'],self.initial['snapshot']['sourceRecords'],self.initial['profile'],0)
        for n,expected in [(affected,'partial'),(clean,'complete')]:
            rid=packet['records'][n]['id'];assessment=next(a for a in snapshot['assessments'] if a['targets'][0]['id']==rid)
            self.assertEqual(assessment['status'],expected)
    def test_unresolved_blocking_finding_is_preserved_per_record(self):
        h=self.initial['receipts']['history'];item=copy.deepcopy(h['stages'][0]);packet=item['input']['lockedInput'];output=item['proposal']['output']
        n=next(n for n,r in enumerate(output['spanDispositions']) if r['status'] in {'represented','represented_uncertain'});rid=packet['records'][n]['id']
        output['findings'].append({'id':'urn:al-isabah:trial:conformance:finding:extra','targets':[{'kind':'sourceRecords','id':rid}],
             'category':'source','severity':'blocking','disposition':'unresolved','evidenceArtifactIds':['urn:al-isabah:trial:artifact:authority']})
        result=projection.completion_evidence(output,packet,rid,[output['spanDispositions'][n]])
        self.assertEqual(result['status'],'partial');self.assertEqual(len(result['blockingFindingIds']),1)
    def test_only_exact_classified_baseline_legacy_concern_gets_management_exception(self):
        h=self.initial['receipts']['history'];item=copy.deepcopy(h['stages'][0]);packet=item['input']['lockedInput'];output=item['proposal']['output']
        n=next(n for n,r in enumerate(output['spanDispositions']) if r['status'] in {'represented','represented_uncertain'});rid=packet['records'][n]['id']
        packet['records'][n]['retainedFindings']=[{'category':'legacy-review-finding','priority':'review'}]
        concern=output['concerns'][n];concern.update(status='open',category='source',rationale='Synthetic opaque inherited provenance gap.')
        output['retainedFindingCoverage'][n]['status']='retained';fid=output['retainedFindingCoverage'][n]['sourceFindingId']
        ledger=next(r for r in old.retained_ledger(packet) if r['id']==fid)
        mapping={'schema':'al-isabah.local-baseline-provenance-classification.v1','baselineOutputSha256':digest(output),
          'entries':[{'baselineConcernId':concern['id'],'baselineConcernSha256':digest(concern),'sourceFindingId':fid,
                      'sourceFindingEvidenceSha256':ledger['evidenceSha256'],'sourceRecordVersionId':rid,'sourceSpanIds':concern['sourceSpanIds']}]}
        baseline={'stages':[{'output':copy.deepcopy(output)}]}
        classified=projection.baseline_classifications(baseline,packet,mapping,digest(mapping));rows=[output['spanDispositions'][n]]
        result=projection.completion_evidence(output,packet,rid,rows,classified)
        self.assertEqual(result['status'],'complete');self.assertEqual(result['inheritedProvenanceConcernIds'],[concern['id']])
        for category in ('vocabulary','source','fidelity'):
            changed=copy.deepcopy(output);extra={**concern,'id':concern['id']+':new','category':category,'rationale':'New substantive synthetic issue.'}
            changed['concerns'].append(extra);changed['retainedFindingCoverage'][n]['concernIds'].append(extra['id'])
            result=projection.completion_evidence(changed,packet,rid,rows,classified)
            self.assertEqual(result['status'],'partial');self.assertIn(extra['id'],result['substantiveOpenConcernIds'])
        changed=copy.deepcopy(output);changed['retainedFindingCoverage'][n]['concernIds']=[]
        with self.assertRaisesRegex(Rejection,'local-baseline-classification-mismatch'):projection.completion_evidence(changed,packet,rid,rows,classified)
        changed=copy.deepcopy(mapping);changed['entries'][0]['sourceFindingEvidenceSha256']='f'*64
        with self.assertRaisesRegex(Rejection,'local-baseline-classification-mismatch'):projection.baseline_classifications(baseline,packet,changed,digest(changed))
        changed=copy.deepcopy(baseline);changed['stages'][0]['output']['concerns'][n]['rationale']='Tampered baseline'
        self.assertEqual(projection.baseline_classifications(changed,packet,mapping,digest(mapping)),{})
    def test_confirmed_nonclaim_retains_actual_independent_review_role(self):
        from test_knowledge_pilot_validation_v2 import KnowledgePilotValidationV2Tests
        packet,stage,output=KnowledgePilotValidationV2Tests().fixture();stage['stage']=old.STAGES[1];output['stage']=stage['stage'];output['stageInputSha256']=digest(stage)
        row=output['spanDispositions'][0];row.update(status='nonclaim_form',reasonCode='formula_only')
        output['nonclaimReviews']=[{'sourceSpanId':row['sourceSpanId'],'status':'confirmed','rationale':'Synthetic independent confirmation.'}]
        private.validate_output(output,stage,packet)
        profile=projection.profile_value();inventory,records=projection.inventory_value(packet,profile,[packet['records'][0]['id']])
        snapshot=projection.stage_snapshot({'proposal':{'output':output}},packet,inventory,records,profile,1)
        self.assertEqual({a['kind'] for a in snapshot['assessments']},{'independent_review'})
    def test_absent_external_pin_wrong_owner_scope_use_partial_expiry_revocation(self):
        f=self.sample()
        with self.assertRaisesRegex(Rejection,'external-pin-mismatch'):self.verify(f,expected_pin='')
        with self.assertRaisesRegex(Rejection,'local-owner-mismatch'):self.verify(f,authority_id='different-owner')
        with self.assertRaisesRegex(Rejection,'local-authorization-revoked'):self.verify(f,revoked=[f['trust']['upstreamAuthorizationSha256']])
        cases=[('scope',lambda a:a['requestedLogicalRecordIds'].pop(),'local-authorization-scope-mismatch'),
               ('use',lambda a:a.update(allowedUses=['local_noncommercial_narrative']),'local-use-not-approved'),
               ('tier',lambda a:a.update(allowedUseTiers=['not_for_narrative']),'local-use-tier-not-approved'),
               ('partial',lambda a:a.update(acceptPartial=False),'local-partial-not-approved'),
               ('expiry',lambda a:a.update(validity={'policy':'bounded','notBefore':'2026-01-01T00:00:00Z','notAfter':'2026-01-01T12:00:00Z'}),'local-authorization-expired'),
               ('subject',lambda a:a.update(subjectSha256='f'*64),'local-authorization-subject-mismatch')]
        for name,change,reason in cases:
            with self.subTest(name=name):
                f=self.sample();change(f['authorization']);self.seal_authorization(f)
                with self.assertRaisesRegex(Rejection,reason):self.verify(f)
    def test_raw_bytes_must_decode_to_exact_payload_even_after_reapproval(self):
        f=self.sample();other={**f['export'],'coverage':{**f['export']['coverage'],'claims':0}};raw=canonical(other)
        self.repin(f,raw)
        with self.assertRaisesRegex(Rejection,'batch-content-mismatch'):self.verify(f,raw_export=raw)
        f=self.sample();raw=(json.dumps(f['export'],ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        with self.assertRaisesRegex(Rejection,'external-pin-mismatch'):self.verify(f,raw_export=raw)
        self.repin(f,raw);self.verify(f,raw_export=raw)
    def test_history_projection_and_binding_tampering_rejected_with_fresh_outer_pins(self):
        for change in (lambda f:f['receipts']['history']['report'].update(status='complete'),
                       lambda f:f['receipts']['history']['stages'][0]['proposal']['output']['recordReviews'][0].update(rationale='Tampered actual stage'),
                       lambda f:f['receipts']['receipts'][0].update(derivedBy='worker'),
                       lambda f:f['receipts']['bindings'][0]['outputs']['objects'].pop()):
            f=self.sample();change(f);self.repin(f)
            with self.assertRaises(Rejection):self.verify(f)
    def test_enclosing_authorization_cannot_appear_indirectly_in_subject_objects(self):
        pin=self.initial['trust']['upstreamAuthorizationSha256']
        for value in ({'nested':{'authorizationSha256':pin}},{'artifacts':[{'sha256':pin}]}):
            with self.assertRaisesRegex(Rejection,'local-authorization-cycle'):authorization.forbid_authorization_cycle(value,pin)
    def test_profile_is_exact_registered_capability_not_arbitrary_external_hash(self):
        f=self.sample();f['profile']['predicates'][0]['epistemicPolicy']['allowedPolarities']=['positive']
        f['snapshot']['profileSha256']=digest(f['profile']);self.repin(f)
        with self.assertRaisesRegex(Rejection,'local-profile-not-registered'):self.verify(f)
    def test_shared_positive_artifacts_reproduce_exactly(self):
        from knowledge_local_support import corpus
        corpus()

    def test_projection_versions_change_with_code_but_source_identities_do_not(self):
        item=self.initial['receipts']['history']['stages'][0];packet=item['input']['lockedInput'];requested=sorted(r['id'] for r in packet['records'])
        results=[]
        for code in ('a'*64,'b'*64):
            with mock.patch.object(projection,'projection_code_digest',return_value=code):
                inventory,records=projection.inventory_value(packet,self.initial['profile'],requested)
                stage=projection.stage_snapshot(item,packet,inventory,records,self.initial['profile'],0)
                results.append((inventory,records,stage))
        self.assertEqual(results[0][1],results[1][1])
        for key in ('sourceUnits','sourceSpans','logicalRecords'):self.assertEqual(results[0][0][key],results[1][0][key])
        self.assertFalse({a['id'] for a in results[0][2]['assessments']}&{a['id'] for a in results[1][2]['assessments']})
        for kind in old.COLLECTIONS:
            one={v['id']:v for v in results[0][2][kind]};two={v['id']:v for v in results[1][2][kind]}
            for identity in one.keys()&two.keys():self.assertEqual(one[identity],two[identity])

    def test_shared_authorization_negative_corpus(self):
        corpus=read(old.ROOT/'tests/fixtures/knowledge-export-v2-local1/adversarial-cases.json')
        for case in corpus['cases']:
            with self.subTest(case=case['id']):
                f=self.sample();operator=copy.deepcopy(corpus['operator']);root={'authorization':f['authorization'],'operator':operator}
                parts=case['target'].split('.');obj=root
                for key in parts[:-1]:obj=obj[key]
                if case['operation']=='remove_last':obj[parts[-1]].pop()
                elif case['operation']=='current_pin':obj[parts[-1]]=[f['trust']['upstreamAuthorizationSha256']]
                else:obj[parts[-1]]=copy.deepcopy(case['value'])
                if case['rebindAuthorization']:self.seal_authorization(f)
                with self.assertRaisesRegex(Rejection,case['producerReason']):self.verify(f,**operator)

    def test_cli_prepares_unsigned_candidate_and_requires_external_approval(self):
        with tempfile.TemporaryDirectory(dir=old.ROOT/'.runtime') as temp:
            root=Path(temp);history=self.initial['receipts']['history'];requested=self.initial['receipts']['requestedSourceRecordVersionIds']
            old.write_new(root/'history.json',history);old.write_new(root/'requested.json',requested)
            args=['local','prepare','--directory',str(root/'candidate'),'--history',str(root/'history.json'),'--requested-records',str(root/'requested.json')]
            with mock.patch.object(old,'require_runtime_directory'),mock.patch('sys.argv',args):self.assertEqual(local.main(),0)
            request=read(root/'candidate/authorization-request.json');self.assertNotIn('authorityId',request);self.assertFalse((root/'candidate/trust.json').exists())
            with mock.patch.object(old,'require_runtime_directory'),mock.patch('sys.argv',['local','verify','--directory',str(root/'candidate')]):self.assertEqual(local.main(),1)


if __name__=='__main__':unittest.main()
