#!/usr/bin/env python3
"""Gate known semantic progress from a separately reviewed seed; never grant admission."""
import argparse
import copy
import hashlib
from pathlib import Path

import knowledge_pilot_remediation as remediation
import knowledge_pilot_validation_v2 as private
from knowledge_export import read,digest,shape,schema_vocabulary,reject,Rejection

old=remediation.old
SCHEMA=old.ROOT/'schemas/knowledge-coverage-gate.v1.schema.json'
KINDS=('claims','events','reports','values')
PINS=('sourceArtifactSha256','packetSha256','baselineOutputSha256','profileSha256',
      'seedSha256','originReportSha256')


def _maps(output):return {kind:{v['id']:v for v in output[kind]} for kind in old.COLLECTIONS}


def _entity(identity,maps):return maps['entities'][identity]['logicalEntityId']


def _core(kind,value,maps):
    """Compare modeled meaning without IDs, concern labels or epistemic relabels."""
    def ref(row):
        if row['kind']=='entities':return ('entity',_entity(row['id'],maps))
        if row['kind']=='events':return ('event',_core('events',maps['events'][row['id']],maps))
        if row['kind']=='values':return ('value',_core('values',maps['values'][row['id']],maps))
        if row['kind']=='places':
            place=maps['places'][row['id']]
            return ('place',_entity(place['entityId'],maps),place['certainty'])
        if row['kind']=='times':
            time=maps['times'][row['id']]
            return ('time',tuple(time[k] for k in ('calendar','earliest','latest','precision','approximate')))
        return (row['kind'],row['id'])
    if kind=='claims':
        return digest([kind,value['predicateId'],ref(value['subjectRef']),ref(value['objectRef']),
                       sorted(value['sourceRecordVersionIds']),sorted(value['sourceSpanIds'])])
    if kind=='events':
        return digest([kind,value['typeId'],sorted((p['roleId'],_entity(p['entityId'],maps)) for p in value['participantRoles']),
                       sorted(value['sourceRecordVersionIds']),
                       sorted((_entity(maps['places'][p]['entityId'],maps),maps['places'][p]['certainty']) for p in value['placeIds']),
                       sorted(tuple(maps['times'][t][k] for k in ('calendar','earliest','latest','precision','approximate')) for t in value['timeIds'])])
    if kind=='reports':
        return digest([kind,sorted(value['sourceRecordVersionIds']),sorted(value['sourceSpanIds']),
                       sorted(_entity(x,maps) for x in value['attributorEntityIds']),
                       [(x['position'],x['role'],sorted(_entity(e,maps) for e in x['entityIds']),bool(x['ambiguityGroupIds'])) for x in value['transmission']]])
    return digest([kind,*[value[k] for k in ('kind','amountNumerator','amountDenominator','unit','approximate')],
                   sorted(value['sourceRecordVersionIds'])])


def _qualification_signature(claim,maps):
    def qualified(identity):
        q=maps['qualifications'][identity]
        return digest([sorted(_entity(e,maps) for e in q['evaluatorEntityIds']),
                       q['criticalStatus'],q['evidentiaryStrength'],q['transmissionStrength'],
                       sorted(q['sourceRecordVersionIds'])])
    def attribution(identity):
        row=maps['attributions'][identity]
        return digest([row['kind'],row['required'],sorted(row['artifactIds']),
                       sorted(_entity(e,maps) for e in row['entityIds'])])
    return (sorted(qualified(x) for x in claim['qualificationIds']),
            sorted(digest({k:v for k,v in maps['useRestrictions'][x].items() if k!='id'})
                   for x in claim['useRestrictionIds']),
            sorted(attribution(x) for x in claim['attributionIds']),
            sorted(_core('reports',maps['reports'][r],maps) for r in claim['reportIds']),
            bool(claim['ambiguityGroupIds']),
            claim['polarity'],claim['modality'],claim['assertionClass'])


def _anchor_for(kind,value,span_id,maps):
    if kind in ('claims','reports'):return span_id in value['sourceSpanIds']
    if kind=='events':return any(span_id in maps['reports'][r]['sourceSpanIds'] for r in value['reportIds'])
    return any(c['objectRef']=={'kind':'values','id':value['id']} and span_id in c['sourceSpanIds']
               for c in maps['claims'].values())


def _route(value,maps):
    return (tuple(sorted(_entity(x,maps) for x in value['attributorEntityIds'])),
            tuple((x['position'],x['role'],tuple(sorted(_entity(e,maps) for e in x['entityIds'])))
                  for x in value['transmission']))


def _expected(kind,value,specs,before,after):
    for spec in specs:
        if spec['kind']!=kind:continue
        name=spec['semanticId']
        if kind=='claims' and value['predicateId']==name:return True
        if kind=='events' and value['typeId']==name:return True
        if kind=='values' and value['kind']+'|'+value['unit']==name:return True
        if kind=='reports' and name=='new_transmission_or_attribution':
            prior={_route(r,before) for r in before['reports'].values()
                   if set(r['sourceRecordVersionIds'])&set(value['sourceRecordVersionIds'])}
            if _route(value,after) not in prior:return True
    return False


def _uncertain(kind,value,maps):
    if kind=='claims':
        return (bool(value['ambiguityGroupIds']) or value['polarity']=='absence_of_evidence'
                or any(maps['qualifications'][q]['criticalStatus']!='unqualified'
                       or maps['qualifications'][q]['evidentiaryStrength']!='source_supported'
                       or maps['qualifications'][q]['transmissionStrength']!='unassessed'
                       for q in value['qualificationIds'])
               )
    if kind=='reports':
        return bool(value['ambiguityGroupIds']) or any(t['role']=='unresolved' or t['ambiguityGroupIds'] for t in value['transmission'])
    if kind=='events':return bool(value['ambiguityGroupIds']) or any(_uncertain('reports',maps['reports'][r],maps) for r in value['reportIds'])
    return value['approximate']


def validate(packet,partition,profile,baseline_input,baseline_output,candidate_input,proposal,seed,ledger,pins):
    if set(pins)!=set(PINS):reject('coverage-independent-pins-required')
    old.validate_packet(packet,partition)
    if (pins['sourceArtifactSha256']!=packet['sourceArtifactSha256']
        or pins['packetSha256']!=packet['packetSha256']
        or pins['baselineOutputSha256']!=digest(baseline_output)
        or pins['profileSha256']!=digest(profile) or pins['seedSha256']!=digest(seed)):
        reject('coverage-independent-pin-mismatch')
    if (baseline_input['lockedInput']!=packet or candidate_input['lockedInput']!=packet
        or baseline_input['profile']!=profile or candidate_input['profile']!=profile):
        reject('coverage-stage-input-mismatch')
    private.validate_output(baseline_output,baseline_input,packet)
    if candidate_input['baseline']['stages'][-1]['output']!=baseline_output:
        reject('coverage-baseline-mismatch')
    remediation.validate_proposal(proposal,candidate_input,packet)
    candidate=proposal['output']
    if candidate['status']=='complete':reject('coverage-premature-completion')
    schema=read(SCHEMA)
    schema_vocabulary(schema)
    shape(seed,schema['$defs']['seed'],schema);shape(ledger,schema['$defs']['ledger'],schema)
    common={k:pins[k] for k in ('sourceArtifactSha256','packetSha256','baselineOutputSha256','profileSha256')}
    if (any(seed[k]!=v or ledger[k]!=v for k,v in common.items())
        or seed['originReportSha256']!=pins['originReportSha256']
        or ledger['seedSha256']!=pins['seedSha256']
        or ledger['candidateOutputSha256']!=digest(candidate)):
        reject('coverage-sidecar-pin-mismatch')
    records={r['id']:r for r in packet['records']}
    spans={s['id']:(s,u['sourceRecordVersionId']) for u in packet['units'] for s in u['spans']}
    if seed['requestedSourceRecordVersionIds']!=sorted(records):reject('coverage-seed-scope-mismatch')
    obligations={x['id']:x for x in seed['obligations']}
    if len(obligations)!=len(seed['obligations']):reject('coverage-duplicate-obligation')
    for row in obligations.values():
        if row['recordId'] not in records or any(s not in spans or spans[s][1]!=row['recordId'] for s in row['sourceSpanIds']):
            reject('coverage-seed-scope-mismatch')
        if row['kind']=='semantic_gap' and not row['expectedSemantics']:
            reject('coverage-expected-semantics-missing')
        for spec in row['expectedSemantics']:
            name=spec['semanticId'];kind=spec['kind']
            if (not name or (kind=='claims' and name not in {p['id'] for p in profile['predicates']})
                or (kind=='events' and name not in profile['eventTypes'])
                or (kind=='values' and not any(name==k+'|'+u['id']
                    for u in profile['valueUnits'] for k in u['valueKinds']))
                or (kind=='reports' and name!='new_transmission_or_attribution')):
                reject('coverage-expected-semantics-invalid')
    anchors={x['id']:x for x in ledger['sourceAnchors']}
    if len(anchors)!=len(ledger['sourceAnchors']):reject('coverage-duplicate-anchor')
    for anchor in anchors.values():
        span=spans.get(anchor['sourceSpanId'])
        if span is None or anchor['recordId']!=span[1]:reject('coverage-anchor-scope-mismatch')
        raw=span[0]['rawOpeniti'];start=anchor['startChar'];end=anchor['endChar']
        if not 0<=start<end<=len(raw) or hashlib.sha256(raw[start:end].encode('utf-8')).hexdigest()!=anchor['surfaceSha256']:
            reject('coverage-anchor-content-mismatch')
        if (anchor['scope']=='coarse')!=(start==0 and end==len(raw)):
            reject('coverage-anchor-scope-mismatch')
    outcomes={x['obligationId']:x for x in ledger['outcomes']}
    if len(outcomes)!=len(ledger['outcomes']) or set(outcomes)!=set(obligations):reject('coverage-outcome-loss')
    before=_maps(baseline_output);after=_maps(candidate)
    previous={kind:{_core(kind,v,before) for v in before[kind].values()} for kind in KINDS}
    successors={(r['after']['kind'],r['after']['id']):r for r in proposal['objectSuccessors']}
    for (kind,identity),row in successors.items():
        if kind not in KINDS:continue
        original=before[kind][row['before']['id']];replacement=after[kind][identity]
        if _core(kind,original,before)!=_core(kind,replacement,after):reject('coverage-successor-semantic-loss')
        if kind=='claims' and _qualification_signature(original,before)!=_qualification_signature(replacement,after):
            reject('coverage-qualification-loss')
        if kind=='events' and (bool(original['ambiguityGroupIds'])!=bool(replacement['ambiguityGroupIds'])
                               or sorted(_core('reports',before['reports'][r],before) for r in original['reportIds'])
                               !=sorted(_core('reports',after['reports'][r],after) for r in replacement['reportIds'])):
            reject('coverage-qualification-loss')
        if kind=='reports' and bool(original['ambiguityGroupIds'])!=bool(replacement['ambiguityGroupIds']):
            reject('coverage-qualification-loss')
    progress=[];qualified=[];unresolved=[]
    for oid,row in outcomes.items():
        obligation=obligations[oid]
        if row['status']=='unresolved':
            if row['objectRefs'] or row['sourceAnchorIds'] or row['reasonCode'] not in obligation['allowedUnresolvedReasons']:
                reject('coverage-unresolved-reason-mismatch')
            unresolved.append(oid);continue
        if obligation['kind']=='candidate_only' or row['reasonCode'] or not row['objectRefs'] or not row['sourceAnchorIds']:
            reject('coverage-candidate-or-outcome-mismatch')
        selected=[]
        for aid in row['sourceAnchorIds']:
            anchor=anchors.get(aid)
            if anchor is None or anchor['recordId']!=obligation['recordId'] or anchor['sourceSpanId'] not in obligation['sourceSpanIds']:
                reject('coverage-anchor-scope-mismatch')
            selected.append(anchor)
        material=False;has_uncertainty=False
        for ref in row['objectRefs']:
            kind=ref['kind'];value=after[kind].get(ref['id'])
            if value is None or obligation['recordId'] not in value['sourceRecordVersionIds']:
                reject('coverage-dangling-object')
            if not any(_anchor_for(kind,value,a['sourceSpanId'],after) for a in selected):
                reject('coverage-object-anchor-mismatch')
            material|=((kind,ref['id']) not in successors and _core(kind,value,after) not in previous[kind]
                       and _expected(kind,value,obligation['expectedSemantics'],before,after))
            has_uncertainty|=_uncertain(kind,value,after)
        if row['status']=='qualified_uncertainty':
            if not has_uncertainty:reject('coverage-uncertainty-unbound')
            qualified.append(oid)
        if obligation['kind']=='semantic_gap' and material:progress.append(oid)
    if not progress:reject('coverage-no-material-progress')
    return {'schema':'al-isabah.knowledge-coverage-gate-result.v1','status':'partial_progress',
            'seedSha256':digest(seed),'ledgerSha256':digest(ledger),'candidateOutputSha256':digest(candidate),
            'materialObligationIds':sorted(progress),'qualifiedUncertaintyObligationIds':sorted(qualified),
            'unresolvedObligationIds':sorted(unresolved),'exhaustiveCoverage':False,
            'humanReview':'unreviewed','independentSemanticReview':'pending',
            'consumerAdmissionAuthorized':False,
            'publicReleaseAuthorized':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('packet','partition','profile','baseline-input','baseline-proposal','candidate-input',
                 'candidate-proposal','seed','ledger','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    for name in PINS:parser.add_argument('--'+''.join('-'+c.lower() if c.isupper() else c for c in name).lstrip('-'),required=True)
    args=parser.parse_args()
    try:
        pins={name:getattr(args,''.join('_'+c.lower() if c.isupper() else c for c in name).lstrip('_')) for name in PINS}
        result=validate(read(args.packet),read(args.partition),read(args.profile),
                        read(args.baseline_input),read(args.baseline_proposal)['output'],read(args.candidate_input),
                        read(args.candidate_proposal),read(args.seed),read(args.ledger),pins)
        old.require_runtime_directory(args.output.parent)
        base=old.ROOT/'.runtime/knowledge/issue-0089'
        if any(args.output.resolve().is_relative_to((base/name).resolve())
               for name in ('trial','adapter-recovery','remediation-draft3-e2a8985','remediation-sol-high-dbb54fa')):
            reject('coverage-separate-output-required')
        old.write_new(args.output,result)
        print(digest(result));return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError,IndexError,AttributeError):
        print('coverage-gate-rejected');return 1


if __name__=='__main__':raise SystemExit(main())
