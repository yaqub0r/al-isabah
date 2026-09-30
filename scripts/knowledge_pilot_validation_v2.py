#!/usr/bin/env python3
"""Draft3 private output validation only; no launch, approval, or receipt writer."""
from pathlib import Path
import knowledge_export_v2_draft3 as export_contract
from knowledge_export import read,shape,digest,reject
from knowledge_predicate_v3 import validate_profile_domains,validate_value_place_domains,validate_claim_domain
from knowledge_pilot_trial import COLLECTIONS,REVIEW_AXES,STAGES,retained_ledger,artifact_inputs,validate_real_identities
import assemble_knowledge_pilot as assembly
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/'schemas/knowledge-pilot-stage-output.v2.schema.json'


def validate_output(output,stage_input,packet):
    shape(output,read(SCHEMA))
    if output['stage']!=stage_input['stage'] or output['stageInputSha256']!=digest(stage_input) or output['packetSha256']!=packet['packetSha256']:reject('trial-output-input-mismatch')
    spans={s['id']:{**s,'sourceRecordVersionId':u['sourceRecordVersionId'],'unitKind':u['kind'],'sourceUnitId':u['id']} for u in packet['units'] for s in u['spans']}
    records={r['id']:r for r in packet['records']}
    maps={key:export_contract.indexed(output[key]) for key in COLLECTIONS}
    maps.update(sourceRecords={rid:{**r,'authorityUnitIds':r['sourceUnitIds'],'sourceArtifactId':'urn:al-isabah:trial:artifact:authority'} for rid,r in records.items()},sourceSpans=spans,sourceUnits={u['id']:u for u in packet['units']},artifacts=export_contract.indexed(artifact_inputs(packet)),assessments={},actors={},logicalRecords={})
    ids=[identity for key in COLLECTIONS for identity in maps[key]]
    if len(ids)!=len(set(ids)):reject('immutable-id-conflict')
    for key in COLLECTIONS:export_contract.validate_refs(output[key],maps)
    if stage_input['fixtureClass']!='synthetic-conformance':
        validate_real_identities(output)
        if any(not identity.startswith('urn:al-isabah:trial:') for identity in ids):reject('trial-proposal-identity-mismatch')
    for prior in stage_input.get('priorOutputs',[]):
        for kind in COLLECTIONS:
            old=export_contract.indexed(prior[kind])
            if any(v['id'] in old and old[v['id']]!=v for v in output[kind]):reject('trial-immutable-id-conflict')
    def owned(span_ids,record_ids):
        if not record_ids or any(s not in spans or spans[s]['sourceRecordVersionId'] not in record_ids for s in span_ids):reject('trial-source-binding-mismatch')
    export_contract.validate_names(maps,owned)
    for key in COLLECTIONS:
        for value in output[key]:
            if 'sourceRecordVersionIds' in value and not value['sourceRecordVersionIds']:reject('trial-source-binding-mismatch')
            if value.get('assessmentIds') or value.get('identityAssessmentIds') or value.get('criticalAssessmentIds'):reject('trial-assessment-inferred')
            if key=='names' and value['derivation']=='editorial_supply':reject('trial-editorial-supply-unbound')
    mentions=maps['mentions'];evidence={x['mentionId']:x for x in output['mentionEvidence']}
    if len(evidence)!=len(output['mentionEvidence']) or set(evidence)!=set(mentions):reject('trial-mention-evidence-mismatch')
    for identity,mention in mentions.items():
        evidence_row=evidence[identity]
        if evidence_row['sourceSpanId']!=mention['sourceSpanId']:reject('trial-mention-evidence-mismatch')
        raw=spans[mention['sourceSpanId']]['rawOpeniti'];a=evidence_row['startChar'];b=evidence_row['endChar']
        if not 0<=a<b<=len(raw) or assembly.sha(raw[a:b].encode('utf-8'))!=mention['surfaceSha256']:reject('trial-mention-evidence-mismatch')
        owned([mention['sourceSpanId']],[mention['sourceRecordVersionId']])
        if identity not in maps['entities'][mention['entityId']]['mentionIds']:reject('reference-closure-mismatch')
    logical_ids=[e['logicalEntityId'] for e in maps['entities'].values()]
    if len(logical_ids)!=len(set(logical_ids)):reject('logical-identity-conflict')
    for entity in maps['entities'].values():
        if not entity['sourceRecordVersionIds'] or any(mentions[m]['entityId']!=entity['id'] for m in entity['mentionIds']):reject('reference-closure-mismatch')
    profile=stage_input['profile']
    if stage_input['profileSha256']!=digest(profile) or stage_input['outputSchemaSha256']!=digest(read(SCHEMA)) or stage_input['outputSchema']!=read(SCHEMA):reject('trial-schema-profile-mismatch')
    shape(profile,read(export_contract.SCHEMA_PATH)['$defs']['profile'],read(export_contract.SCHEMA_PATH))
    validate_profile_domains(profile);validate_value_place_domains(maps,profile)
    predicates=export_contract.indexed(profile['predicates'])
    for claim in maps['claims'].values():
        owned(claim['sourceSpanIds'],claim['sourceRecordVersionIds'])
        if not claim['sourceSpanIds'] or not claim['reportIds'] or not claim['qualificationIds'] or not claim['attributionIds'] or not claim['useRestrictionIds']:reject('trial-claim-evidence-missing')
        pred=predicates.get(claim['predicateId'])
        if pred is None:reject('unapproved-predicate')
        validate_claim_domain(claim,pred,maps)
        if any(claim['id'] not in maps['reports'][r]['claimIds'] for r in claim['reportIds']):reject('reference-closure-mismatch')
        quals=[maps['qualifications'][q] for q in claim['qualificationIds']]
        if any({'kind':'claims','id':claim['id']} not in q['targets'] for q in quals):reject('qualification-loss')
        factual=any(maps['useRestrictions'][u]['tier']=='factual_spine' for u in claim['useRestrictionIds'])
        if factual and (claim['polarity']=='absence_of_evidence' or claim['assertionClass']!='source_attested' or claim['modality']!='asserted' or claim['ambiguityGroupIds'] or any(q['criticalStatus']!='unqualified' or q['evidentiaryStrength']!='source_supported' for q in quals)):reject('qualification-loss')
    for report in maps['reports'].values():
        owned(report['sourceSpanIds'],report['sourceRecordVersionIds'])
        if not report['sourceSpanIds'] or any(report['id'] not in maps['claims'][c]['reportIds'] for c in report['claimIds']):reject('reference-closure-mismatch')
        if [t['position'] for t in report['transmission']]!=list(range(len(report['transmission']))):reject('transmission-order-mismatch')
        if any((t['role']=='unresolved' and not t['ambiguityGroupIds']) or (t['role']!='unresolved' and not t['entityIds']) for t in report['transmission']):reject('qualification-loss')
    for event in maps['events'].values():
        if event['typeId'] not in profile['eventTypes'] or any(p['roleId'] not in profile['participantRoles'] for p in event['participantRoles']):reject('unapproved-role')
    for time in maps['times'].values():
        if time['earliest']>time['latest']:reject('time-interval-invalid')
    for group in maps['ambiguityGroups'].values():
        expected={(kind,v['id']) for kind in COLLECTIONS for v in maps[kind].values() if group['id'] in v.get('ambiguityGroupIds',[])}
        if expected!={(r['kind'],r['id']) for r in group['members']}:reject('ambiguity-incomplete')
    rows={x['sourceSpanId']:x for x in output['spanDispositions']}
    if len(rows)!=len(output['spanDispositions']) or set(rows)!=set(spans):reject('trial-span-coverage-mismatch')
    reasons={'represented':{'mapped'},'represented_uncertain':{'uncertain'},'structural_only':{'heading'},'nonclaim_form':{'formula_only','bibliographic_format'},'unsupported_semantics':{'unsupported'},'unprocessed':{'pending'},'source_or_mapping_blocked':{'source_damage','mapping_unverified'}}
    for sid,row in rows.items():
        export_contract.validate_refs(row,maps)
        if row['reasonCode'] not in reasons[row['status']]:reject('disposition-mismatch')
        if row['status']=='structural_only' and spans[sid]['unitKind']=='entry':reject('disposition-mismatch')
        if row['status'] in {'represented','represented_uncertain'} and not row['claimIds'] and not row['reportIds']:reject('disposition-mismatch')
        if row['status']=='represented_uncertain' and not row['ambiguityGroupIds']:reject('ambiguity-incomplete')
        if row['status'] in {'structural_only','nonclaim_form','unprocessed'} and (row['claimIds'] or row['reportIds']):reject('disposition-mismatch')
        for kind,field in [('claims','claimIds'),('reports','reportIds')]:
            expected={v['id'] for v in maps[kind].values() if sid in v['sourceSpanIds']}
            if set(row[field])!=expected:reject('reference-closure-mismatch')
    nonclaims={r['sourceSpanId']:r for r in output['nonclaimReviews']}
    if len(nonclaims)!=len(output['nonclaimReviews']) or set(nonclaims)!={sid for sid,r in rows.items() if r['status']=='nonclaim_form'}:reject('trial-nonclaim-review-missing')
    for row in nonclaims.values():
        if not row['rationale'].strip() or (output['stage']==STAGES[0] and row['status']!='proposed') or (output['stage']!=STAGES[0] and row['status']=='proposed'):reject('trial-nonclaim-review-missing')
    reviews={r['sourceRecordVersionId']:r for r in output['recordReviews']}
    if len(reviews)!=len(output['recordReviews']) or set(reviews)!=set(records):reject('trial-record-review-coverage-mismatch')
    for review in reviews.values():
        if not review['rationale'].strip():reject('trial-review-evidence-missing')
        export_contract.validate_refs(review,maps)
    concerns=export_contract.indexed(output['concerns'])
    for concern in concerns.values():
        if not concern['sourceSpanIds'] or not set(concern['sourceSpanIds'])<=set(spans) or not concern['rationale'].strip():reject('trial-review-evidence-missing')
    finding_rows={x['sourceFindingId']:x for x in output['retainedFindingCoverage']}
    if len(finding_rows)!=len(output['retainedFindingCoverage']) or set(finding_rows)!={f['id'] for f in retained_ledger(packet)}:reject('trial-retained-finding-loss')
    for row in finding_rows.values():
        if not row['concernIds'] or not set(row['concernIds'])<=set(concerns):reject('trial-retained-finding-loss')
        if row['status']=='resolved' and any(concerns[c]['status']!='resolved' for c in row['concernIds']):reject('trial-false-resolution')
    if output['status']=='complete' and (any(r['status'] in export_contract.BLOCKED for r in rows.values()) or any(r[k]!='checked' for r in reviews.values() for k in REVIEW_AXES) or any(c['status']=='open' for c in concerns.values()) or any(f['severity']=='blocking' and f['disposition']=='unresolved' for f in maps['findings'].values()) or any(r['status']=='unresolved' for r in nonclaims.values())):reject('trial-false-completion')
    return output



def main():
    import argparse
    from knowledge_export import Rejection
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--proposal',type=Path,required=True);args=p.parse_args()
    try:
        stage_input=read(args.input);output=read(args.proposal)
        validate_output(output,stage_input,stage_input['lockedInput'])
        print(output['status']);print(digest(output));return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError):print('draft3-stage-validation-rejected');return 1


if __name__=='__main__':raise SystemExit(main())
