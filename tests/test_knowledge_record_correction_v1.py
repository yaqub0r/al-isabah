"""Fictional correction conformance; no model launch or user decision is made."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[1]/'tests')]
import knowledge_record_accounting_v1 as accounting
import knowledge_record_correction_v1 as correction
from knowledge_export import digest,Rejection
import test_knowledge_gated_successor as fixture
import test_knowledge_local_gated_history_v1 as history_fixture


class RecordAccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.GatedSuccessorTests.setUpClass()

    def setUp(self):
        self.packet=fixture.GatedSuccessorTests.packet
        self.output=fixture.GatedSuccessorTests.final
        self.rid=fixture.GatedSuccessorTests.record_id
        self.scope={'recordId':self.rid}
        units=[u for u in self.packet['units'] if u['sourceRecordVersionId']==self.rid]
        atoms=[];routes=[]
        for unit in units:
            for span in unit['spans']:
                reports=[r for r in self.output['reports'] if self.rid in r['sourceRecordVersionIds']
                         and span['id'] in r['sourceSpanIds']]
                claims=[c for c in self.output['claims'] if self.rid in c['sourceRecordVersionIds']
                        and span['id'] in c['sourceSpanIds']]
                refs=[{'kind':'reports','id':r['id']} for r in reports]
                refs += [{'kind':'claims','id':c['id']} for c in claims]
                refs += [{'kind':'events','id':e['id']} for e in self.output['events']
                         if self.rid in e['sourceRecordVersionIds'] and
                         any(r['id'] in e['reportIds'] for r in reports)]
                if unit['kind']=='entry' and span==unit['spans'][0]:
                    refs += [{'kind':'values','id':v['id']} for v in self.output['values']
                             if self.rid in v['sourceRecordVersionIds']]
                kind='structural' if unit['kind']!='entry' else 'semantic' if refs else 'nonsemantic'
                disposition='structural' if kind=='structural' else 'represented' if refs else 'nonsemantic'
                atom={'id':'atom-'+str(len(atoms)),'sourceSpanId':span['id'],'startChar':0,
                      'endChar':len(span['rawOpeniti']),
                      'surfaceSha256':hashlib.sha256(span['rawOpeniti'].encode()).hexdigest(),
                      'kind':kind,'disposition':disposition,'objectRefs':refs,'findingIds':[],
                      'reasonCode':'heading' if kind=='structural' else '' if refs else 'formula_only',
                      'rationale':'Synthetic accounting fixture.'}
                atoms.append(atom)
                for report in reports:
                    routes.append({'routeKey':report['id'],'atomIds':[atom['id']],
                                   'reportId':report['id'],'findingIds':[],
                                   'status':'represented','rationale':'Synthetic route.'})
        self.accounting={'schema':accounting.SCHEMA,'recordId':self.rid,
                         'packetSha256':self.packet['packetSha256'],
                         'sourceUnitSha256':{u['id']:u['rawSha256'] for u in sorted(units,key=lambda x:x['id'])},
                         'atoms':sorted(atoms,key=lambda x:(x['sourceSpanId'],x['startChar'])),
                         'routes':sorted(routes,key=lambda x:x['routeKey']),'recordComplete':False}
        self.review={'schema':accounting.REVIEW_SCHEMA,'accountingSha256':digest(self.accounting),
                     'candidateOutputSha256':digest(self.output),
                     'atomVerdicts':[{'atomId':a['id'],'verdict':'supported','rationale':'Checked.'}
                                     for a in self.accounting['atoms']],
                     'routeVerdicts':[{'routeKey':r['routeKey'],'verdict':'supported','rationale':'Checked.'}
                                      for r in self.accounting['routes']],
                     'completenessAssessment':'no_missing_known','rationale':'Fictional review.'}

    def test_complete_partition_routes_and_review(self):
        accounting.validate(self.accounting,self.packet,self.output,self.scope)
        self.assertEqual(accounting.validate_review(self.review,self.accounting,self.packet,
                                                    self.output,self.scope),'no_missing_known')
        final=copy.deepcopy(self.accounting);final['recordComplete']=True
        self.assertTrue(accounting.validate_final(final,self.accounting,self.review,self.packet,
                                                  self.output,self.output,self.scope)['recordComplete'])
        self.assertFalse(accounting.validate_final(self.accounting,self.accounting,self.review,self.packet,
                                                   self.output,self.output,self.scope)['recordComplete'])

    def test_gap_route_and_false_completeness_rejected(self):
        gap=copy.deepcopy(self.accounting);gap['atoms'][0]['startChar']=1
        with self.assertRaises(Rejection):accounting.validate(gap,self.packet,self.output,self.scope)
        missing=copy.deepcopy(self.accounting);missing['routes'].pop()
        with self.assertRaisesRegex(Rejection,'accounting-route-coverage'):
            accounting.validate(missing,self.packet,self.output,self.scope)
        residual=copy.deepcopy(self.review);residual['atomVerdicts'][0]['verdict']='missing'
        residual['completenessAssessment']='residuals'
        final=copy.deepcopy(self.accounting);final['recordComplete']=True
        with self.assertRaisesRegex(Rejection,'accounting-false-completeness'):
            accounting.validate_final(final,self.accounting,residual,self.packet,
                                      self.output,self.output,self.scope)

    def test_other_record_graph_is_frozen(self):
        other=next(r for r in self.output['reports'] if self.rid not in r['sourceRecordVersionIds'])
        changed=copy.deepcopy(self.output)
        next(r for r in changed['reports'] if r['id']==other['id'])['summary']='Unrelated edit'
        with self.assertRaisesRegex(Rejection,'correction-nontarget-object-change'):
            correction.validate_record_edits(self.output,changed,self.packet,
                {'recordId':self.rid,'allowedCrossRecordRefs':[]})

    def test_new_target_finding_and_owned_sidecars_are_allowed(self):
        changed=copy.deepcopy(self.output)
        finding=copy.deepcopy(changed['findings'][0]);finding['id']='urn:al-isabah:synthetic:finding:new-target'
        finding['targets']=[{'kind':'sourceRecords','id':self.rid}]
        changed['findings'].append(finding)
        entity=next(x for x in changed['entities'] if x['sourceRecordVersionIds']==[self.rid])
        attribution=copy.deepcopy(changed['attributions'][0]);attribution['id']='urn:al-isabah:synthetic:attribution:target'
        attribution['entityIds']=[entity['id']];changed['attributions'].append(attribution)
        claim=next(x for x in changed['claims'] if x['sourceRecordVersionIds']==[self.rid])
        new_claim=copy.deepcopy(claim);new_claim['id']='urn:al-isabah:synthetic:claim:owned'
        restriction=copy.deepcopy(changed['useRestrictions'][0]);restriction['id']='urn:al-isabah:synthetic:restriction:owned'
        new_claim['useRestrictionIds']=[restriction['id']]
        changed['claims'].append(new_claim);changed['useRestrictions'].append(restriction)
        correction.validate_record_edits(self.output,changed,self.packet,
            {'recordId':self.rid,'allowedCrossRecordRefs':[]})

    def test_shared_cross_record_and_global_findings_are_frozen(self):
        other=next(r['id'] for r in self.packet['records'] if r['id']!=self.rid)
        artifact=correction.prior.original.old.artifact_inputs(self.packet)[0]['id']
        for targets in ([{'kind':'sourceRecords','id':other}],
                        [{'kind':'sourceRecords','id':self.rid},{'kind':'sourceRecords','id':other}],
                        [{'kind':'artifacts','id':artifact}]):
            changed=copy.deepcopy(self.output)
            finding=copy.deepcopy(changed['findings'][0]);finding['id']='urn:al-isabah:synthetic:finding:unowned'
            finding['targets']=targets;changed['findings'].append(finding)
            with self.assertRaisesRegex(Rejection,'correction-nontarget-object-change'):
                correction.validate_record_edits(self.output,changed,self.packet,
                    {'recordId':self.rid,'allowedCrossRecordRefs':[]})
        changed=copy.deepcopy(self.output)
        restriction=copy.deepcopy(changed['useRestrictions'][0]);restriction['id']='urn:al-isabah:synthetic:restriction:global'
        changed['useRestrictions'].append(restriction)
        with self.assertRaisesRegex(Rejection,'correction-nontarget-object-change'):
            correction.validate_record_edits(self.output,changed,self.packet,
                {'recordId':self.rid,'allowedCrossRecordRefs':[]})

    def test_record_completion_respects_only_unchanged_legacy_concern(self):
        packet=copy.deepcopy(self.packet);output=copy.deepcopy(self.output)
        record=next(r for r in packet['records'] if r['id']==self.rid)
        record['retainedFindings'][0]['category']='legacy-review-finding'
        fid=correction.prior.original.old.retained_ledger(packet)
        fid=next(x['id'] for x in fid if x['sourceRecordVersionId']==self.rid)
        spans={s['id'] for u in packet['units'] if u['sourceRecordVersionId']==self.rid for s in u['spans']}
        concern=next(x for x in output['concerns'] if spans.intersection(x['sourceSpanIds']))
        concern['status']='open';original=copy.deepcopy(concern)
        row=next(x for x in output['retainedFindingCoverage'] if x['sourceFindingId']==fid)
        if concern['id'] not in row['concernIds']:row['concernIds'].append(concern['id'])
        classifications={concern['id']:{'binding':{'sourceFindingId':fid},'originalConcern':original}}
        scope={'recordId':self.rid,'targetObligationIds':['O-SYNTHETIC']}
        ledger={'outcomes':[{'obligationId':'O-SYNTHETIC','status':'represented'}]}
        self.assertNotIn('open_concerns',correction.record_completion_blockers(
            output,packet,scope,ledger,classifications))
        concern['rationale']+=' Changed.'
        self.assertIn('open_concerns',correction.record_completion_blockers(
            output,packet,scope,ledger,classifications))
        concern.update(original)
        next(x for x in output['recordReviews'] if x['sourceRecordVersionId']==self.rid)['structureCoverage']='unresolved'
        self.assertIn('review_axes',correction.record_completion_blockers(
            output,packet,scope,ledger,classifications))
        next(x for x in output['recordReviews'] if x['sourceRecordVersionId']==self.rid)['structureCoverage']='checked'
        next(x for x in output['spanDispositions'] if x['sourceSpanId'] in spans)['status']='unprocessed'
        self.assertIn('owned_spans',correction.record_completion_blockers(
            output,packet,scope,ledger,classifications))
        next(x for x in output['spanDispositions'] if x['sourceSpanId'] in spans)['status']='represented_uncertain'
        output['nonclaimReviews'].append({'sourceSpanId':next(iter(spans)),'status':'unresolved'})
        self.assertIn('nonclaim_review',correction.record_completion_blockers(
            output,packet,scope,ledger,classifications))
        output['nonclaimReviews'].clear()
        finding=copy.deepcopy(output['findings'][0]);finding.update(id='urn:al-isabah:synthetic:finding:blocking',
            severity='blocking',disposition='unresolved',targets=[{'kind':'sourceRecords','id':self.rid}])
        output['findings'].append(finding)
        self.assertIn('blocking_findings',correction.record_completion_blockers(
            output,packet,scope,ledger,classifications))


class SyntheticWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):history_fixture.GatedHistoryTests.setUpClass()

    def setUp(self):
        self.source=history_fixture.GatedHistoryTests('test_descendant_head_replays_three_successes_and_four_launches')
        self.source.setUp();self.addCleanup(self.source.doCleanups)
        history=self.source.history;packet=history['context']['packet']
        rid=self.source.source.fixture.record_id
        record=next(r for r in packet['records'] if r['id']==rid)
        units={u['id']:u for u in packet['units'] if u['sourceRecordVersionId']==rid}
        scope={'schema':correction.SCOPE_SCHEMA,'recordId':rid,'sourceOrdinal':record['sourceOrdinal'],
               'legacyRecordId':record.get('legacyRecordId',record['id']),'ownedSourceUnitIds':sorted(record['sourceUnitIds']),
               'ownedStructuralUnitIds':sorted(k for k,u in units.items() if u['kind']!='entry'),
               'inheritedContextUnitIds':sorted(record.get('inheritedContextUnitIds',[])),
               'targetObligationIds':['O-SYNTHETIC-NEW-ACT'],'allowedCrossRecordRefs':[]}
        normalized=correction.replay.validate_history(history,self.source.pins)
        seed=correction.seed_candidate(history['context']['seed'],normalized)
        seed['status']='reviewed_for_gate'
        self.patch=mock.patch.object(correction.prior.original.old,'require_runtime_directory')
        self.patch.start();self.addCleanup(self.patch.stop)
        self.code=mock.patch.object(correction,'code_identity',return_value={'synthetic':'0'*64})
        self.code.start();self.addCleanup(self.code.stop)
        self.ctx=correction.context(history,self.source.pins,scope,seed,
                                    self.source.source.workdir/'correction')
        self.commit='d'*40
        self.req=correction.request(self.ctx,self.commit)
        self.decision={'schema':correction.DECISION_SCHEMA,'request':self.req,'approval':'approved',
                       'origin':{'kind':'actual_user_message','threadId':correction.prior.original.old.COORDINATOR,
                                 'userTurnReference':'SYNTHETIC-CONFORMANCE-ONLY',
                                 'recordedBy':'trusted_coordinator'}}
        self.pin=digest(self.decision)
        self.task=history['context']['first']['receipt']['task']

    def make_accounting(self,output,complete=False):
        fixture_accounting=RecordAccountingTests('test_complete_partition_routes_and_review')
        fixture_accounting.setUp()
        value=copy.deepcopy(fixture_accounting.accounting)
        sid=self.source.source.fixture.span_id
        for atom in value['atoms']:
            if atom['sourceSpanId']==sid:
                for event in output['events']:
                    if self.ctx['scope']['recordId'] in event['sourceRecordVersionIds']:
                        ref={'kind':'events','id':event['id']}
                        if ref not in atom['objectRefs']:atom['objectRefs'].append(ref)
        value['recordComplete']=complete
        return value

    def make_ledger(self,proposal):
        ledger=copy.deepcopy(self.ctx['history']['adjudication']['ledger'])
        ledger['baselineOutputSha256']=digest(self.ctx['normalized']['stages'][-1]['proposal']['output'])
        ledger['seedSha256']=digest(self.ctx['seed'])
        ledger['candidateOutputSha256']=digest(proposal['output'])
        sid=self.source.source.fixture.span_id
        span=next(s for u in self.ctx['normalized']['packet']['units'] for s in u['spans'] if s['id']==sid)
        anchor={'id':'synthetic-correction-anchor','recordId':self.ctx['scope']['recordId'],
                'sourceSpanId':sid,'startChar':0,'endChar':len(span['rawOpeniti']),
                'surfaceSha256':hashlib.sha256(span['rawOpeniti'].encode()).hexdigest(),'scope':'coarse'}
        ledger['sourceAnchors'].append(anchor)
        row=next(x for x in ledger['outcomes'] if x['obligationId']=='O-SYNTHETIC-NEW-ACT')
        row.update(status='represented',objectRefs=[{'kind':'events','id':proposal['output']['events'][-1]['id']}],
                   sourceAnchorIds=[anchor['id']],reasonCode='')
        return ledger

    def make_review(self,accounting_value,output):
        return {'schema':accounting.REVIEW_SCHEMA,'accountingSha256':digest(accounting_value),
                'candidateOutputSha256':digest(output),
                'atomVerdicts':[{'atomId':a['id'],'verdict':'supported','rationale':'Synthetic check.'}
                                for a in accounting_value['atoms']],
                'routeVerdicts':[{'routeKey':r['routeKey'],'verdict':'supported','rationale':'Synthetic check.'}
                                 for r in accounting_value['routes']],
                'completenessAssessment':'no_missing_known','rationale':'Fictional independent check.'}

    def make_item(self,name,prior_items):
        stage=correction.stage_input(name,self.ctx,self.commit,self.decision,self.pin,prior_items)
        previous=(prior_items[-1]['proposal']['output'] if prior_items else
                  self.ctx['normalized']['stages'][-1]['proposal']['output'])
        proposal=self.source.source.fixture.proposal(stage,previous,add_event=not prior_items)
        sidecar=self.make_accounting(proposal['output'],complete=name==correction.STAGES[-1])
        item={'input':stage,'proposal':proposal,'accounting':sidecar,'receipt':None}
        if name==correction.STAGES[1]:
            item['critique']=self.make_review(sidecar,proposal['output'])
        else:
            item['ledger']=self.make_ledger(proposal)
            if name==correction.STAGES[0]:item['gate']=correction.gate_result(self.ctx,stage,proposal,item['ledger'])
            else:
                review=prior_items[1]
                evidence=accounting.validate_final(sidecar,review['accounting'],review['critique'],
                    self.ctx['normalized']['packet'],review['proposal']['output'],proposal['output'],self.ctx['scope'])
                item['gate']=correction.final_gate(self.ctx,stage,proposal,item['ledger'],evidence)
        directory=Path(self.ctx['directory'])
        correction.prior.original.old.write_new(directory/(name+'.input.json'),stage)
        item['reservation']=correction.reserve_once(name,self.ctx,self.commit,self.decision,self.pin,prior_items)
        session='synthetic-correction-'+str(len(prior_items)+1)
        log=self.source.source.worker_log(session,phase='final_answer')
        item['attempt']=correction.bind_once(name,log,session,'turn',self.task,self.ctx,self.commit,
                                              self.decision,self.pin,prior_items)
        item['receipt']=correction.capture(name,item,self.ctx,self.commit,self.decision,self.pin,prior_items)
        return item

    def test_three_fresh_stages_and_seven_total_slots(self):
        stages=[]
        for name in correction.STAGES:stages.append(self.make_item(name,stages))
        report=correction.report(self.ctx,self.commit,self.decision,self.pin,stages)
        self.assertEqual(len(report['launchAttempts']),7)
        self.assertEqual(report['status'],'partial')
        self.assertTrue(report['recordComplete'])
        self.assertFalse(report['exhaustiveVolumeCoverage'])
        blocked=copy.deepcopy(stages[-1]['proposal']['output'])
        target=next(r for r in blocked['recordReviews'] if r['sourceRecordVersionId']==self.ctx['scope']['recordId'])
        target['structureCoverage']='unresolved'
        self.assertIn('review_axes',correction.record_completion_blockers(blocked,
            self.ctx['normalized']['packet'],self.ctx['scope'],stages[-1]['ledger']))
        blocked_proposal=copy.deepcopy(stages[-1]['proposal']);blocked_proposal['output']=blocked
        blocked_ledger=copy.deepcopy(stages[-1]['ledger'])
        blocked_ledger['candidateOutputSha256']=digest(blocked)
        reviewed={'recordComplete':True,'accountingSha256':digest(stages[-1]['accounting']),
                  'reviewSha256':digest(stages[1]['critique'])}
        with self.assertRaisesRegex(Rejection,'correction-false-record-completeness'):
            correction.final_gate(self.ctx,stages[-1]['input'],blocked_proposal,blocked_ledger,reviewed)
        partial=correction.final_gate(self.ctx,stages[-1]['input'],blocked_proposal,blocked_ledger,
                                      {**reviewed,'recordComplete':False})
        self.assertFalse(partial['recordComplete'])
        self.assertIn('review_axes',partial['recordCompletionBlockers'])
        stale=copy.deepcopy(self.ctx['seed']);stale['baselineOutputSha256']='0'*64
        with self.assertRaisesRegex(Rejection,'correction-rebased-seed-not-reviewed-or-drift'):
            correction.validate_rebased_seed(stale,self.ctx['history']['context']['seed'],self.ctx['normalized'])
        wrong_scope=copy.deepcopy(self.ctx['scope']);wrong_scope['sourceOrdinal']+=1
        with self.assertRaisesRegex(Rejection,'correction-scope-source-drift'):
            correction.check_scope(wrong_scope,self.ctx['normalized']['packet'],self.ctx['seed'],
                self.ctx['history']['adjudication']['ledger'],
                self.ctx['normalized']['stages'][-1]['proposal']['output'])
        false_ledger=copy.deepcopy(stages[-1]['ledger'])
        false_ledger['outcomes'][0]['status']='unresolved'
        with self.assertRaises(Rejection):
            correction.final_gate(self.ctx,stages[-1]['input'],stages[-1]['proposal'],false_ledger,
                {'recordComplete':True,'accountingSha256':digest(stages[-1]['accounting']),
                 'reviewSha256':digest(stages[1]['critique'])})
        with self.assertRaisesRegex(Rejection,'correction-slot-already-consumed'):
            correction.reserve_once(correction.STAGES[0],self.ctx,self.commit,self.decision,self.pin,[])
