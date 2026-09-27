import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from knowledge_export_support import ROOT, k, uid, seal, fixture, successor, export, admission


class KnowledgeExportTests(unittest.TestCase):
    def setUp(self):
        self.snapshot, self.trust = fixture()

    def fails(self, code, call):
        with self.assertRaisesRegex(k.Rejection, '^' + code + '$'):
            call()

    def test_two_batches_replay_and_overlap_have_exact_unique_accounting(self):
        first = export(self.snapshot, self.trust, 1)
        second = export(self.snapshot, self.trust, 2)
        self.assertEqual(first['coverage'], {
            'sourceScopeRecordCount': 30, 'approvedSourceRecordCount': 3,
            'semanticExtractedRecordCount': 2, 'semanticCompleteRecordCount': 0,
            'approvedClaimCount': 2, 'requestedRecordCount': 1,
            'dependencyRecordCount': 1, 'totalRecordCount': 2,
            'requestedClaimCount': 1, 'dependencyClaimCount': 1, 'totalClaimCount': 2})
        history = [admission(b, self.snapshot, self.trust) for b in (first,second)]
        result = k.replay(history)
        self.assertEqual(k.replay(history + history), result)
        self.assertEqual(k.replay(list(reversed(history))), result)
        self.assertEqual(result['batchCount'], 2)
        self.assertEqual(result['uniqueRecordCount'], 2)
        self.assertEqual(result['uniqueClaimCount'], 2)
        self.assertEqual(first['claims'], second['claims'])

    def test_missing_extraction_is_disclosed_not_invented(self):
        batch = export(self.snapshot, self.trust, 3)
        self.assertEqual(batch['claims'], [])
        self.assertEqual(batch['coverage']['requestedRecordCount'], 1)
        self.assertEqual(batch['coverage']['requestedClaimCount'], 0)

    def test_complete_cross_volume_ambiguity_closure(self):
        batch = export(self.snapshot, self.trust, 1)
        self.assertEqual(batch['selection']['volumes'], [1])
        self.assertEqual([r['volume'] for r in batch['sourceRecords']], [1,2])
        self.assertEqual(batch['ambiguityGroups'][0]['memberClaimIds'], [uid('claim',1), uid('claim',2)])
        batch['claims'].pop()
        batch['payloadSha256'] = k.digest({key:value for key,value in batch.items() if key != 'payloadSha256'})
        self.fails('batch-content-mismatch', lambda: k.validate_batch(batch,self.snapshot,self.trust['snapshotSha256'],self.trust['pins']))

    def test_unavailable_ambiguity_dependency_fails_closed(self):
        self.snapshot['claims'].pop()
        self.trust = seal(self.snapshot)
        self.fails('missing-reference', lambda: export(self.snapshot,self.trust,1))

    def test_missing_record_entity_group_and_event_references(self):
        for kind in ('record','entity','group','event'):
            snapshot = copy.deepcopy(self.snapshot)
            if kind == 'record': snapshot['claims'][0]['sourceRecordIds'] = [uid('record',99)]
            elif kind == 'entity': snapshot['claims'][0]['subjectId'] = uid('entity',99)
            elif kind == 'group': snapshot['claims'][0]['ambiguityGroupIds'] = [uid('group',99)]
            else: snapshot['lifecycleEvents'] = [{'id':uid('event',1),'kind':'withdraws','targetClaimId':uid('claim',99),'replacementClaimIds':[]}]
            with self.subTest(kind=kind):
                trust=seal(snapshot)
                self.fails('missing-reference',lambda: export(snapshot,trust,1))

    def test_asymmetric_ambiguity_membership_rejected(self):
        self.snapshot['claims'][0]['ambiguityGroupIds'] = []
        self.trust=seal(self.snapshot)
        self.fails('ambiguity-incomplete',lambda: export(self.snapshot,self.trust,1))

    def test_correction_supersession_withdrawal_and_historical_replay(self):
        base=export(self.snapshot,self.trust,1)
        for kind in ('corrects','supersedes','withdraws'):
            with self.subTest(kind=kind):
                snapshot,trust=successor(self.snapshot,kind)
                new=export(snapshot,trust,4)
                history=[admission(base,self.snapshot,self.trust),admission(new,snapshot,trust)]
                result=k.replay(history)
                self.assertIn(uid('claim',1),result['retiredClaimIds'])
                self.assertNotIn(uid('claim',1),result['activeClaimIds'])
                self.assertEqual(k.replay(history+[history[0]]),result)
                self.assertEqual(result['uniqueClaimCount'],2 if kind=='withdraws' else 3)

    def test_lifecycle_cannot_reuse_existing_claim_as_replacement(self):
        snapshot,trust=successor(self.snapshot)
        snapshot['lifecycleEvents'][0]['replacementClaimIds']=[uid('claim',2)]
        trust=seal(snapshot)
        history=[admission(export(self.snapshot,self.trust,1),self.snapshot,self.trust),
                 admission(export(snapshot,trust,4),snapshot,trust)]
        self.fails('lifecycle-conflict',lambda:k.replay(history))

    def test_corrected_snapshot_bootstraps_with_retired_evidence_only(self):
        for kind in ('corrects','supersedes','withdraws'):
            snapshot,trust=successor(self.snapshot,kind)
            result=k.replay([admission(export(snapshot,trust,4),snapshot,trust)])
            self.assertIn(uid('claim',1),result['retiredClaimIds'])
            self.assertNotIn(uid('claim',1),result['activeClaimIds'])

    def test_lifecycle_cycle_self_link_and_repeated_target(self):
        for kind in ('self','cycle','repeat','empty'):
            snapshot,trust=successor(self.snapshot)
            event=snapshot['lifecycleEvents'][0]
            if kind=='self': event['replacementClaimIds']=[uid('claim',1)]
            elif kind=='empty': event['replacementClaimIds']=[]
            else:
                snapshot['lifecycleEvents'].append({'id':uid('event',2),'kind':'corrects',
                    'targetClaimId':uid('claim',3 if kind=='cycle' else 1),'replacementClaimIds':[uid('claim',1 if kind=='cycle' else 2)]})
            trust=seal(snapshot)
            with self.subTest(kind=kind):
                self.fails('lifecycle-conflict',lambda:export(snapshot,trust,4))

    def test_no_changed_immutable_claim_record_entity_group_release_or_batch_ids(self):
        base=export(self.snapshot,self.trust,1)
        for collection,field,value in [('claims','transmissionStrength','criticized'),
            ('sourceRecords','pages',[11]),('entities','sourceRecordIds',[uid('record',2)]),
            ('ambiguityGroups','presentationMode','qualified_ambiguity_context'),
            ('sourceRelease','assetSha256','f'*64),('batch','volumes',[1,2])]:
            snapshot=copy.deepcopy(self.snapshot)
            snapshot['admission']['id']=uid('admission',9)
            if collection=='sourceRelease': snapshot[collection][field]=value
            elif collection=='batch':
                snapshot['batches'][0]['recordIds'].append(uid('record',2))
                snapshot['batches'][0][field]=value
            else: snapshot[collection][0][field]=value
            if collection != 'batch': snapshot['batches'][0]['id']=uid('batch',9)
            trust=seal(snapshot)
            new=export(snapshot,trust,1 if collection=='batch' else 9)
            with self.subTest(collection=collection):
                self.fails('immutable-id-conflict',lambda:k.replay([admission(base,self.snapshot,self.trust),admission(new,snapshot,trust)]))

    def test_external_snapshot_and_pin_tampering(self):
        self.fails('snapshot-digest-mismatch',lambda:k.build(self.snapshot,uid('batch',1),'f'*64,self.trust['pins']))
        for key in self.trust['pins']:
            trust=copy.deepcopy(self.trust)
            trust['pins'][key]='f'*64
            with self.subTest(pin=key):
                self.fails('policy-digest-mismatch',lambda:export(self.snapshot,trust,1))
        snapshot=copy.deepcopy(self.snapshot)
        snapshot['admission']['approvedCollectionsSha256']='f'*64
        trust={'snapshotSha256':k.digest(snapshot),'pins':k.pins(snapshot,k.read(k.SCHEMA_PATH))}
        self.fails('admission-digest-mismatch',lambda:export(snapshot,trust,1))

    def test_release_aliases_and_policy_cannot_change_under_existing_identity(self):
        base=export(self.snapshot,self.trust,1)
        for field in ('assetSha256','proposalSha256','closureSha256','policy','rights','id'):
            snapshot=copy.deepcopy(self.snapshot)
            snapshot['admission']['id']=uid('admission',9)
            snapshot['batches'][0]['id']=uid('batch',9)
            if field=='policy': snapshot['policy']['id']=uid('policy',2)
            elif field=='rights': snapshot['rights']['attributionIds']=[uid('attribution',2)]
            elif field=='id':
                snapshot['sourceRelease']['id']=uid('release',2)
                for record in snapshot['sourceRecords']: record['sourceReleaseId']=uid('release',2)
            else: snapshot['sourceRelease'][field]='f'*64
            trust=seal(snapshot)
            new=export(snapshot,trust,9)
            with self.subTest(field=field):
                self.fails('immutable-id-conflict',lambda:k.replay([admission(base,self.snapshot,self.trust),admission(new,snapshot,trust)]))

    def test_fixed_authority_revision_ledger_rejects_implicit_transition(self):
        snapshot=copy.deepcopy(self.snapshot)
        snapshot['authority']['revisionId']=uid('revision',2)
        snapshot['batches'][0]['id']=uid('batch',9)
        trust=seal(snapshot)
        self.fails('source-identity-mismatch',lambda:k.replay([
            admission(export(self.snapshot,self.trust,1),self.snapshot,self.trust),
            admission(export(snapshot,trust,9),snapshot,trust)]))

    def test_approval_identity_cannot_be_rebound(self):
        snapshot,trust=successor(self.snapshot)
        snapshot['admission']['id']=self.snapshot['admission']['id']
        trust=seal(snapshot)
        self.fails('immutable-id-conflict',lambda:k.replay([
            admission(export(self.snapshot,self.trust,1),self.snapshot,self.trust),
            admission(export(snapshot,trust,4),snapshot,trust)]))

    def test_payload_hash_and_coverage_tampering(self):
        batch=export(self.snapshot,self.trust,1)
        batch['coverage']['totalClaimCount']=99
        self.fails('payload-digest-mismatch',lambda:k.validate_batch(batch,self.snapshot,self.trust['snapshotSha256'],self.trust['pins']))
        batch['payloadSha256']=k.digest({key:value for key,value in batch.items() if key!='payloadSha256'})
        self.fails('batch-content-mismatch',lambda:k.validate_batch(batch,self.snapshot,self.trust['snapshotSha256'],self.trust['pins']))

    def test_no_prohibited_payload_or_value_echo_at_any_layer(self):
        for key in ('arabicBody','translationBody','quotation','privateEvidence','modelTrace','credentials','archive','displayName','SECRET_KEY_IN_DIAGNOSTIC'):
            for collection in ('root',*k.COLLECTIONS):
                snapshot=copy.deepcopy(self.snapshot)
                if collection=='lifecycleEvents': snapshot,_=successor(snapshot)
                target=snapshot if collection=='root' else snapshot[collection][0]
                target[key]='SECRET_VALUE_IN_DIAGNOSTIC'
                trust=seal(snapshot)
                with self.subTest(key=key,collection=collection):
                    self.fails('prohibited-payload',lambda:export(snapshot,trust,1))

    def test_invalid_ids_never_normalized_or_used_as_prose(self):
        for value in ('urn:al-isabah:synthetic:claim:a b','raw Arabic العربية','C:/private/path','https://private.example','sk_live_abcdefghijklmnop','urn:al-isabah:synthetic:claim:x\n'):
            snapshot=copy.deepcopy(self.snapshot)
            snapshot['claims'][0]['id']=value
            trust=seal(snapshot)
            self.fails('prohibited-payload',lambda:export(snapshot,trust,1))

    def test_exact_case_sensitive_entity_ids_remain_distinct(self):
        snapshot=copy.deepcopy(self.snapshot)
        for n,suffix in [(0,'A'),(1,'a')]:
            old=snapshot['entities'][n]['id']; new=uid('entity',suffix)
            snapshot['entities'][n]['id']=new
            for claim in snapshot['claims']:
                for key in ('subjectId','objectId'):
                    if claim[key]==old: claim[key]=new
        trust=seal(snapshot)
        self.assertEqual({e['id'] for e in export(snapshot,trust,1)['entities']},{uid('entity','A'),uid('entity','a')})

    def test_credentials_cannot_hide_inside_syntactically_valid_ids(self):
        self.snapshot['entities'][0]['id']=uid('entity','sk_live_abcdefghijklmnop')
        self.trust=seal(self.snapshot)
        self.fails('prohibited-payload',lambda:export(self.snapshot,self.trust,1))

    def test_qualification_not_promoted_by_machine_pass_or_human_review(self):
        self.snapshot['sourceRecords'][0]['humanReview']='verified'
        self.snapshot['claims'][0]['storyUseTier']='factual_spine'
        self.trust=seal(self.snapshot)
        self.fails('qualification-loss',lambda:export(self.snapshot,self.trust,1))

    def test_unreviewed_and_needs_attention_preserved(self):
        batch=export(self.snapshot,self.trust,1)
        self.assertEqual(batch['sourceRecords'][0]['humanReview'],'unreviewed')
        self.assertEqual(batch['sourceRecords'][0]['machineAssessment'],'needs_attention')
        self.assertEqual(batch['sourceRecords'][0]['canonicalPromotion'],'blocked')

    def test_wrong_types_unknown_predicate_schema_and_real_mode_rejected(self):
        for change in ('bool','string','array','predicate','version','mode'):
            snapshot=copy.deepcopy(self.snapshot)
            if change=='bool': snapshot['sourceRecords'][0]['volume']=True
            elif change=='string': snapshot['sourceRecords'][0]['pages']='10'
            elif change=='array': snapshot['claims']={}
            elif change=='predicate': snapshot['claims'][0]['predicateId']=uid('predicate','unsupported')
            elif change=='version': snapshot['schemaVersion']='2.0.0'
            else: snapshot['mode']='production'
            trust=seal(snapshot)
            self.fails('unapproved-predicate' if change=='predicate' else 'schema-mismatch',lambda:export(snapshot,trust,1))

    def test_schema_has_no_open_objects_or_unbounded_strings(self):
        def visit(value):
            if isinstance(value,dict):
                if value.get('type')=='object': self.assertIs(value.get('additionalProperties'),False)
                if value.get('type')=='string': self.assertTrue(set(value)&{'const','enum','pattern'})
                for child in value.values(): visit(child)
            elif isinstance(value,list):
                for child in value: visit(child)
        visit(k.read(k.SCHEMA_PATH))

    def test_unsupported_schema_constraints_fail_closed(self):
        for keyword,value in [('oneOf',[]),('format','uri'),('minLength',2),('exclusiveMinimum',1)]:
            schema=k.read(k.SCHEMA_PATH)
            schema['$defs']['claim']['properties']['id'][keyword]=value
            self.fails('unsupported-schema',lambda:k.shape({},schema))
        self.fails('unsupported-schema',lambda:k.shape(0,{'minimum':1}))
        self.fails('unsupported-schema',lambda:k.shape(0,{'$ref':'#/$defs/missing'}))

    def test_semantic_hash_is_not_an_exact_file_hash(self):
        import hashlib
        canonical=k.canonical(self.snapshot)
        formatted=json.dumps(self.snapshot,indent=2).replace('\n','\r\n').encode('utf8')
        self.assertEqual(k.digest(json.loads(formatted)),k.digest(self.snapshot))
        self.assertNotEqual(hashlib.sha256(formatted).hexdigest(),hashlib.sha256(canonical).hexdigest())

    def test_checked_in_examples_reproduce_exact_bytes(self):
        directory=ROOT/'tests/fixtures/knowledge-export-v1'
        self.assertEqual((directory/'snapshot.json').read_bytes(),k.canonical(self.snapshot))
        self.assertEqual((directory/'trust.json').read_bytes(),k.canonical(self.trust))
        for number in (1,2,3):
            self.assertEqual((directory/f'batch-{number}.json').read_bytes(),k.canonical(export(self.snapshot,self.trust,number)))
        for kind in ('corrects','supersedes','withdraws'):
            snapshot,trust=successor(self.snapshot,kind)
            for name,value in [(f'{kind}-snapshot',snapshot),(f'{kind}-trust',trust),(f'{kind}-batch',export(snapshot,trust,4))]:
                self.assertEqual((directory/f'{name}.json').read_bytes(),k.canonical(value))

    def test_cli_check_duplicate_json_and_safe_failure(self):
        directory=ROOT/'tests/fixtures/knowledge-export-v1'
        command=[sys.executable,str(ROOT/'scripts/knowledge_export.py'),'--snapshot',str(directory/'snapshot.json'),
                 '--trust',str(directory/'trust.json'),'--batch',uid('batch',1),'--output',str(directory/'batch-1.json'),'--check']
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.json'
            path.write_text('{"secret":1,"secret":2}',encoding='utf8')
            self.fails('duplicate-key',lambda:k.read(path))
            path.write_text('{"secret":NaN}',encoding='utf8')
            self.fails('invalid-json',lambda:k.read(path))


if __name__=='__main__':
    unittest.main()
