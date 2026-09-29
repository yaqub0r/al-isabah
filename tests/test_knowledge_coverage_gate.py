"""Fictional source and proposals for the bounded successor progress gate."""
import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[1]/'tests')]
from knowledge_local_support import history_fixture
import knowledge_coverage_gate as gate
from knowledge_export import digest,read,Rejection


def fixture():
    history=history_fixture();packet=history['stages'][0]['input']['lockedInput'];partition=history['partition']
    baseline_input=history['stages'][-1]['input'];baseline=history['stages'][-1]['proposal']['output']
    candidate_input=copy.deepcopy(history['stages'][0]['input'])
    candidate_input['baseline']={'stages':[{'output':baseline}]}
    candidate_input['baselineSha256']=digest(candidate_input['baseline'])
    candidate=copy.deepcopy(baseline)
    candidate['stage']=candidate_input['stage'];candidate['stageInputSha256']=digest(candidate_input)
    event=copy.deepcopy(baseline['events'][0]);event['id']='urn:al-isabah:trial:conformance:events:new-death'
    event['typeId']='urn:al-isabah:event-type:death';candidate['events'].append(event)
    proposal={'schema':'al-isabah.knowledge-remediation-proposal.v1','output':candidate,
              'baselineSha256':digest(candidate_input['baseline']),'objectSuccessors':[],
              'concernOutcomes':[{'baselineConcernId':c['id'],'baselineConcernSha256':digest(c),
                 'outcome':'resolved' if c['status']=='resolved' else 'residual','rationale':'Synthetic check only.'}
                 for c in baseline['concerns']]}
    report=next(r for r in candidate['reports'] if r['id'] in event['reportIds'])
    span_id=report['sourceSpanIds'][0];record_id=event['sourceRecordVersionIds'][0]
    spans={s['id']:s for u in packet['units'] for s in u['spans']}
    def anchor(identity,rid,sid):
        raw=spans[sid]['rawOpeniti']
        return {'id':identity,'recordId':rid,'sourceSpanId':sid,'startChar':0,'endChar':len(raw),
                'surfaceSha256':hashlib.sha256(raw.encode('utf-8')).hexdigest(),'scope':'coarse'}
    first=anchor('synthetic-anchor-1',record_id,span_id)
    seed={'schema':'al-isabah.knowledge-coverage-seed.v1','status':'reviewed_for_gate',
          'sourceArtifactSha256':packet['sourceArtifactSha256'],'packetSha256':packet['packetSha256'],
          'baselineOutputSha256':digest(baseline),'profileSha256':digest(baseline_input['profile']),
          'originReportSha256':digest(history['report']),
          'requestedSourceRecordVersionIds':sorted(r['id'] for r in packet['records']),
          'obligations':[{'id':'O-SYNTHETIC-NEW-ACT','recordId':record_id,'sourceSpanIds':[span_id],
                          'kind':'semantic_gap','originSha256':digest(history['report']),
                          'allowedUnresolvedReasons':['not_yet_extracted'],
                          'expectedSemantics':[{'kind':'events','semanticId':'urn:al-isabah:event-type:death'}]} ]}
    ledger={'schema':'al-isabah.knowledge-coverage-ledger.v1',
            **{k:seed[k] for k in ('sourceArtifactSha256','packetSha256','baselineOutputSha256','profileSha256')},
            'seedSha256':digest(seed),'candidateOutputSha256':digest(candidate),
            'sourceAnchors':[first],
            'outcomes':[{'obligationId':'O-SYNTHETIC-NEW-ACT','status':'represented',
                         'objectRefs':[{'kind':'events','id':event['id']}],
                         'sourceAnchorIds':[first['id']],'reasonCode':''}]}
    pins={k:seed[k] for k in ('sourceArtifactSha256','packetSha256','baselineOutputSha256','profileSha256','originReportSha256')}
    pins['seedSha256']=digest(seed)
    return packet,partition,baseline_input,baseline,candidate_input,proposal,seed,ledger,pins


class CoverageGateTests(unittest.TestCase):
    def setUp(self):self.data=fixture()
    def run_gate(self,data=None):
        packet,partition,baseline_input,baseline,candidate_input,proposal,seed,ledger,pins=data or self.data
        return gate.validate(packet,partition,baseline_input['profile'],baseline_input,baseline,
                             candidate_input,proposal,seed,ledger,pins)
    def refresh(self,data):
        ledger=data[7];seed=data[6];proposal=data[5]
        ledger['seedSha256']=digest(seed);ledger['candidateOutputSha256']=digest(proposal['output'])
        data[8]['seedSha256']=digest(seed)

    def test_material_new_act_reports_partial_progress_only(self):
        result=self.run_gate()
        self.assertEqual(result['status'],'partial_progress')
        self.assertEqual(result['materialObligationIds'],['O-SYNTHETIC-NEW-ACT'])
        self.assertFalse(result['exhaustiveCoverage']);self.assertFalse(result['consumerAdmissionAuthorized'])
        self.assertEqual(result['humanReview'],'unreviewed')
        self.assertEqual(result['independentSemanticReview'],'pending')

    def test_unrelated_new_act_cannot_satisfy_same_span_obligation(self):
        data=copy.deepcopy(self.data)
        data[6]['obligations'][0]['expectedSemantics']=[{'kind':'events','semanticId':'urn:al-isabah:event-type:marriage'}]
        self.refresh(data)
        with self.assertRaisesRegex(Rejection,'coverage-no-material-progress'):self.run_gate(data)
        data[6]['obligations'][0]['expectedSemantics'].append({'kind':'events','semanticId':'urn:al-isabah:event-type:death'})
        self.refresh(data)
        self.assertEqual(self.run_gate(data)['materialObligationIds'],['O-SYNTHETIC-NEW-ACT'])

    def test_candidate_fine_anchor_is_validated_from_exact_packet_bytes(self):
        data=copy.deepcopy(self.data);anchor=data[7]['sourceAnchors'][0]
        raw=next(s['rawOpeniti'] for u in data[0]['units'] for s in u['spans'] if s['id']==anchor['sourceSpanId'])
        anchor.update(endChar=len(raw)-1,surfaceSha256=hashlib.sha256(raw[:-1].encode('utf-8')).hexdigest(),scope='fine')
        self.assertEqual(self.run_gate(data)['status'],'partial_progress')

    def test_copy_id_migration_and_concern_relabel_do_not_count(self):
        for change in ('copy','migrate','relabel'):
            data=copy.deepcopy(self.data);baseline=data[3];proposal=data[5];candidate=proposal['output'];ledger=data[7]
            candidate['events']=[e for e in candidate['events'] if e['id']!='urn:al-isabah:trial:conformance:events:new-death']
            ledger['outcomes'][0]['objectRefs']=[{'kind':'events','id':baseline['events'][0]['id']}]
            if change=='migrate':
                old=baseline['events'][0];new=copy.deepcopy(old);new['id']='urn:al-isabah:trial:conformance:events:migrated'
                candidate['events']=[e for e in candidate['events'] if e['id']!=old['id']]+[new]
                proposal['objectSuccessors']=[{'before':{'kind':'events','id':old['id']},'beforeSha256':digest(old),
                    'after':{'kind':'events','id':new['id']},'rationale':'Synthetic ID migration only.'}]
                ledger['outcomes'][0]['objectRefs'][0]['id']=new['id']
            if change=='relabel':
                # A changed outcome label cannot manufacture a modeled act.
                ledger['outcomes'][0]['status']='qualified_uncertainty'
            self.refresh(data)
            with self.assertRaises(Rejection):self.run_gate(data)

    def test_fabricated_or_out_of_scope_anchors_and_dangling_refs_fail(self):
        for change in (
            lambda d:d[7]['sourceAnchors'][0].update(surfaceSha256='f'*64),
            lambda d:d[7]['sourceAnchors'][0].update(sourceSpanId='out-of-scope'),
            lambda d:d[7]['sourceAnchors'][0].update(startChar=1,scope='fine'),
            lambda d:d[7]['outcomes'][0]['objectRefs'][0].update(id='missing-object'),
            lambda d:d[7]['outcomes'][0].update(sourceAnchorIds=['missing-anchor']),
        ):
            data=copy.deepcopy(self.data);change(data);self.refresh(data)
            with self.assertRaises(Rejection):self.run_gate(data)

    def test_independent_pins_and_candidate_only_authority_fail_closed(self):
        data=copy.deepcopy(self.data);data[8]['seedSha256']='f'*64
        with self.assertRaisesRegex(Rejection,'coverage-independent-pin-mismatch'):self.run_gate(data)
        data=copy.deepcopy(self.data);data[6]['obligations'][0]['kind']='candidate_only';self.refresh(data)
        with self.assertRaisesRegex(Rejection,'coverage-candidate-or-outcome-mismatch'):self.run_gate(data)
        data=copy.deepcopy(self.data);data[6]['status']='draft';self.refresh(data)
        with self.assertRaises(Rejection):self.run_gate(data)
        data=copy.deepcopy(self.data);data[7]['outcomes'].clear();self.refresh(data)
        with self.assertRaises(Rejection):self.run_gate(data)

    def test_cli_writes_only_a_new_metadata_result_after_pinned_validation(self):
        data=copy.deepcopy(self.data);packet,partition,baseline_input,baseline,candidate_input,proposal,seed,ledger,pins=data
        base=gate.old.ROOT/'.runtime/knowledge/issue-0089'
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            root=Path(directory);values={'packet':packet,'partition':partition,'profile':baseline_input['profile'],
                'baseline-input':baseline_input,'baseline-proposal':{'output':baseline},
                'candidate-input':candidate_input,'candidate-proposal':proposal,'seed':seed,'ledger':ledger}
            args=['gate']
            for name,value in values.items():
                path=root/(name+'.json');gate.old.write_new(path,value)
                args.extend(['--'+name,str(path)])
            for name,value in pins.items():
                option=''.join('-'+c.lower() if c.isupper() else c for c in name).lstrip('-')
                args.extend(['--'+option,value])
            out=root/'result.json';args.extend(['--output',str(out)])
            with mock.patch('sys.argv',args):self.assertEqual(gate.main(),0)
            self.assertEqual(read(out)['status'],'partial_progress')
            changed=args.copy();changed[-1]=str(root/'rejected.json')
            index=changed.index('--seed-sha256')+1;changed[index]='f'*64
            with mock.patch('sys.argv',changed):self.assertEqual(gate.main(),1)
            self.assertFalse((root/'rejected.json').exists())

    def test_qualified_uncertainty_and_specific_unresolved_reason(self):
        data=copy.deepcopy(self.data);packet=data[0];baseline=data[3];seed=data[6];ledger=data[7]
        claim=next(c for c in baseline['claims'] if c['ambiguityGroupIds'])
        sid=claim['sourceSpanIds'][0];rid=claim['sourceRecordVersionIds'][0]
        raw=next(s['rawOpeniti'] for u in packet['units'] for s in u['spans'] if s['id']==sid)
        ledger['sourceAnchors'].append({'id':'synthetic-anchor-2','recordId':rid,'sourceSpanId':sid,
             'startChar':0,'endChar':len(raw),'surfaceSha256':hashlib.sha256(raw.encode()).hexdigest(),'scope':'coarse'})
        seed['obligations'].extend([
            {'id':'O-SYNTHETIC-QUALIFIED','recordId':rid,'sourceSpanIds':[sid],'kind':'carry_forward',
             'originSha256':digest(baseline),'allowedUnresolvedReasons':['witness_unavailable'],
             'expectedSemantics':[]},
            {'id':'O-SYNTHETIC-PROVENANCE','recordId':rid,'sourceSpanIds':[sid],'kind':'provenance_gap',
             'originSha256':digest(baseline),'allowedUnresolvedReasons':['missing_notice_provenance'],
             'expectedSemantics':[]}])
        ledger['outcomes'].extend([
            {'obligationId':'O-SYNTHETIC-QUALIFIED','status':'qualified_uncertainty',
             'objectRefs':[{'kind':'claims','id':claim['id']}],'sourceAnchorIds':['synthetic-anchor-2'],'reasonCode':''},
            {'obligationId':'O-SYNTHETIC-PROVENANCE','status':'unresolved','objectRefs':[],
             'sourceAnchorIds':[],'reasonCode':'missing_notice_provenance'}])
        self.refresh(data);result=self.run_gate(data)
        self.assertEqual(result['qualifiedUncertaintyObligationIds'],['O-SYNTHETIC-QUALIFIED'])
        self.assertEqual(result['unresolvedObligationIds'],['O-SYNTHETIC-PROVENANCE'])
        data[7]['outcomes'][-1]['reasonCode']='vague';self.refresh(data)
        with self.assertRaisesRegex(Rejection,'coverage-unresolved-reason-mismatch'):self.run_gate(data)


if __name__=='__main__':unittest.main()
