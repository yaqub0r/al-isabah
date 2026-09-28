import copy
import unittest
from knowledge_export_v2_support import ROOT,k,uid,ref,fixture,seal,export,date

class KnowledgeExportV2DraftTests(unittest.TestCase):
 def setUp(self):self.s,self.i,self.p,self.t=fixture()
 def out(self):return export(self.s,self.i,self.p,self.t)
 def reseal(self):self.t=seal(self.s,self.i,self.p)
 def fails(self,code):
  with self.assertRaisesRegex(k.Rejection,'^'+code+'$'):self.out()
 def test_full_snapshot_exact_scope_dependency_and_gap_counts(self):
  b=self.out();self.assertEqual(b['coverage'],{'requestedLogicalRecords':2,'dependencyLogicalRecords':1,'sourceUnits':3,'entries':2,'structuralUnits':1,'expectedSpans':3,'representedSpans':2,'uncertainSpans':1,'blockedSpans':1,'extractionCompleteRecords':1,'assessmentVersions':6,'claims':4,'scopeExtractionComplete':False})
  self.assertEqual(k.validate_payload(b,self.s,self.i,self.p,self.t),b)
 def test_uncertainty_negation_transmission_roles_survive(self):
  b=self.out();self.assertEqual(b['claims'][1]['polarity'],'negative');self.assertEqual(len(b['ambiguityGroups'][0]['members']),2)
  self.assertEqual([x['role'] for x in b['reports'][0]['transmission']],['speaker','transmitter']);self.assertEqual(b['events'][0]['participantRoles'][0]['roleId'],uid('role',1))
 def test_checked_in_fixtures_exact_and_v1_untouched(self):
  d=ROOT/'tests/fixtures/knowledge-export-v2-draft'
  for name,value in [('snapshot',self.s),('inventory',self.i),('profile',self.p),('trust',self.t),('batch',self.out())]:self.assertEqual((d/(name+'.json')).read_bytes(),k.canonical(value))
 def test_real_mode_and_disguised_real_authority_rejected(self):
  for target,key,value in [(self.s,'mode','real'),(self.p,'mode','real'),(self.s,'fixtureClass','not-a-fixture')]:
   old=target[key];target[key]=value;self.reseal();self.fails('real-mode-disabled');target[key]=old
  self.i['authority']['verificationBasis']='licensed_transcription';self.p['authority']=copy.deepcopy(self.i['authority']);self.s['authority']=copy.deepcopy(self.i['authority']);self.reseal();self.fails('real-mode-disabled')
 def test_no_export_self_approval_or_inventory_recount(self):
  self.i['sourceUnits'][0]['rawSha256']='f'*64;self.fails('external-pin-mismatch')
 def test_prohibited_expression_and_duplicate_ids(self):
  self.s['claims'][0]['english']='Synthetic prohibited body';self.reseal();self.fails('prohibited-payload')
  self.s['claims'][0].pop('english');self.s['entities'][1]['id']=self.s['entities'][0]['id'];self.reseal();self.fails('immutable-id-conflict')
 def test_reference_kind_and_missing_targets_fail(self):
  self.s['claims'][0]['objectRef']={'kind':'events','id':uid('entities',2)};self.reseal();self.fails('missing-reference')
  self.s['claims'][0]['objectRef']=ref('events',1);self.reseal();self.fails('reference-kind-mismatch')
 def test_auxiliary_references_all_resolve(self):
  cases=[('mentions','entityId',uid('entities',99)),('events','placeIds',[uid('places',99)]),('claims','qualificationIds',[uid('qualifications',99)]),('claims','attributionIds',[uid('attributions',99)]),('claims','useRestrictionIds',[uid('useRestrictions',99)]),('assessments','findingIds',[uid('findings',99)])]
  for collection,key,value in cases:
   with self.subTest(collection=collection,key=key):
    prior=self.s[collection][0][key];self.s[collection][0][key]=value;self.reseal();self.fails('missing-reference');self.s[collection][0][key]=prior
 def test_missing_span_or_duplicate_disposition_cannot_hide_gap(self):
  original=copy.deepcopy(self.s['spanDispositions']);self.s['spanDispositions'].pop();self.reseal();self.fails('coverage-mismatch')
  self.s['spanDispositions']=original;self.s['spanDispositions'][2]['sourceSpanId']=uid('span',2);self.reseal();self.fails('coverage-mismatch')
 def test_false_extraction_completion_is_rejected(self):
  next(a for a in self.s['assessments'] if a['id']==uid('assessments',4))['status']='complete';self.reseal();self.fails('false-extraction-completion')
 def test_structural_and_nonclaim_misuse_rejected(self):
  self.s['spanDispositions'][2].update(status='structural_only',reasonCode='heading');self.reseal();self.fails('disposition-mismatch')
 def test_span_claim_reverse_closure(self):
  self.s['spanDispositions'][0]['claimIds'].remove(uid('claims',3));self.reseal();self.fails('reference-closure-mismatch')
 def test_cross_volume_alternative_cannot_be_dropped(self):
  self.s['ambiguityGroups'][0]['members']=[ref('claims',1),ref('claims',3)];self.reseal();self.fails('ambiguity-incomplete')
 def test_favorable_qualification_and_unknown_predicate_rejected(self):
  self.s['useRestrictions'][0]['tier']='factual_spine';self.reseal();self.fails('qualification-loss')
  self.s['useRestrictions'][0]['tier']='attributed_disputed_report';self.s['claims'][0]['predicateId']=uid('predicate',999);self.reseal();self.fails('unapproved-predicate')
 def test_transmission_reordering_and_unknown_role_fail(self):
  self.s['reports'][0]['transmission'].reverse();self.reseal();self.fails('transmission-order-mismatch')
  self.s['reports'][0]['transmission'].reverse();self.s['events'][0]['participantRoles'][0]['roleId']=uid('role',99);self.reseal();self.fails('unapproved-role')
 def test_assessment_input_time_and_human_review_binding(self):
  self.s['assessments'][0]['inputs'][0]['sha256']='0'*64;self.reseal();self.fails('assessment-binding-mismatch')
  self.setUp();self.s['assessments'][0]['observedAt']['timestamp']='2000-02-30T00:00:00Z';self.reseal();self.fails('assessment-time-invalid')
  self.setUp();a=next(a for a in self.s['assessments'] if a['kind']=='human_review');a['status']='reviewed';self.reseal();self.fails('human-review-inferred')
 def test_assessment_cycle_and_cross_record_selection_fail(self):
  a=self.s['assessments'][0];a['predecessorIds']=[a['id']];self.reseal();self.fails('lifecycle-conflict')
  a['predecessorIds']=[];self.s['assessmentSelection'][0]['extractionAssessmentId']=uid('assessments',4);self.reseal();self.fails('assessment-binding-mismatch')
 def test_assessment_version_keeps_old_state_and_does_not_refresh_it(self):
  before=copy.deepcopy(self.s['assessments'][0]);new=copy.deepcopy(before);new['id']=uid('assessments',20);new['predecessorIds']=[before['id']];self.s['assessments'].append(new);self.s['assessments'].sort(key=lambda a:a['id']);self.s['assessmentSelection'][0]['extractionAssessmentId']=new['id'];self.reseal();b=self.out()
  self.assertIn(before,b['assessments']);self.assertEqual(b['coverage']['requestedLogicalRecords'],2);self.assertEqual(b['coverage']['assessmentVersions'],7)
 def test_current_selection_cannot_revert_to_predecessor(self):
  old=copy.deepcopy(self.s['assessments'][0]);new=copy.deepcopy(old);new['id']=uid('assessments',20);new['predecessorIds']=[old['id']];self.s['assessments'].append(new);self.s['assessments'].sort(key=lambda x:x['id']);self.reseal();self.fails('stale-assessment-selection')
 def test_exact_replay_and_same_id_changed_bytes(self):
  b=self.out();self.assertEqual(k.replay_identity([b])['uniqueExports'],1);self.assertEqual(k.replay_identity([b,b])['uniqueExports'],1)
  changed=copy.deepcopy(b);changed['claims'][0]['polarity']='negative';changed['payloadSha256']=k.digest({a:v for a,v in changed.items() if a!='payloadSha256'})
  with self.assertRaisesRegex(k.Rejection,'immutable-id-conflict'):k.replay_identity([b,changed])
 def test_batch_declaration_payload_pin_and_subset_fail(self):
  b=self.out();b['claims'].pop();b['payloadSha256']=k.digest({a:v for a,v in b.items() if a!='payloadSha256'})
  with self.assertRaisesRegex(k.Rejection,'batch-content-mismatch'):k.validate_payload(b,self.s,self.i,self.p,self.t)
  self.s['batch']['requestedLogicalRecordIds'].pop();self.reseal();self.fails('batch-declaration-mismatch')
 def test_withdrawal_preserves_ambiguity_and_conflict_rejects(self):
  e={'id':uid('lifecycleEvents',1),'kind':'withdraws','targets':[ref('claims',1)],'replacements':[],'decisionArtifactId':uid('artifacts',4),'effectiveAt':date(True),'dependencyIds':[]};self.s['lifecycleEvents']=[e];self.reseal();b=self.out();self.assertEqual(len(b['ambiguityGroups'][0]['members']),2)
  conflict=copy.deepcopy(e);conflict['id']=uid('lifecycleEvents',2);self.s['lifecycleEvents'].append(conflict);self.reseal();self.fails('lifecycle-conflict')
 def test_entity_target_kind_and_real_identifier_fail_closed(self):
  self.s['claims'][0]['objectRef']=ref('entities',3);self.reseal();self.fails('reference-kind-mismatch')
  self.setUp();self.s['id']='urn:al-isabah:real:snapshot:1';self.reseal();self.fails('real-mode-disabled')
 def test_span_assessment_cannot_borrow_other_record_review(self):
  self.s['spanDispositions'][2]['assessmentIds']=[uid('assessments',2)];self.reseal();self.fails('assessment-binding-mismatch')
 def test_shared_adversarial_corpus_with_freshly_bound_pins(self):
  suite=k.read(ROOT/'tests/fixtures/knowledge-export-v2-draft/adversarial-cases.json')
  for case in suite['cases']:
   with self.subTest(case=case['id']):
    self.setUp();inputs={'snapshot':self.s,'inventory':self.i,'profile':self.p}
    for patch in case['patches']:
     target=inputs[patch['input']]
     for part in patch['path'][:-1]:target=target[part]
     key=patch['path'][-1]
     if patch['op']=='append':target[key].append(copy.deepcopy(patch['value']))
     else:target[key]=copy.deepcopy(patch['value'])
    self.reseal();self.fails(case['expectedCode'])
 def test_source_unit_mapping_and_time_range_fail_closed(self):
  self.s['sourceRecords'][0]['authorityUnitIds']=[uid('unit',3)];self.reseal();self.fails('source-identity-mismatch')
  self.setUp();self.s['times'][0]['earliest']=99;self.reseal();self.fails('time-interval-invalid')

if __name__=='__main__':unittest.main()
