#!/usr/bin/env python3
"""Prepare a metadata-only real pilot; does not read bodies or execute models."""
import argparse
import hashlib
from pathlib import Path
from knowledge_export import canonical,digest,read,reject,Rejection
from public_boundary import boundary_errors
ROOT=Path(__file__).resolve().parents[1]
INVENTORY=ROOT/'evidence/inventories/issue-0089-womens-book.source-scope.v1.json'
AUDIT=ROOT/'evidence/inventories/issue-0089-successor-v8.crosswalk-audit.v1.json'
REGISTRY=ROOT/'profiles/knowledge/execution-methods.v1-draft.json'
OUTPUT=ROOT/'evidence/inventories/issue-0089-knowledge-pilot-preparation.v1.json'
PINS={INVENTORY.name:'001ea04c30fe3e52dec2d38dd49bb087c74a909474715c07e5a41b19237b4062',AUDIT.name:'55448e20f1f8ce43a922c3da11f27cebc270a79bdbd4cee97e8d3ae38451b60b'}
ORDINALS=tuple(range(10754,10764))+(11424,11425,12303)


def build(inventory_path=INVENTORY,audit_path=AUDIT):
    inputs={}
    for path,expected in ((inventory_path,PINS[INVENTORY.name]),(audit_path,PINS[AUDIT.name])):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:reject('pilot-input-pin-mismatch')
        inputs[expected]=read(path)
    inventory=inputs[PINS[INVENTORY.name]];audit=inputs[PINS[AUDIT.name]]
    if digest({k:v for k,v in inventory.items() if k!='inventorySha256'})!=inventory['inventorySha256']:reject('pilot-inventory-digest-mismatch')
    if digest({k:v for k,v in audit.items() if k!='auditSha256'})!=audit['auditSha256']:reject('pilot-audit-digest-mismatch')
    entries=[e for e in inventory['entries'] if e['ordinal'] in ORDINALS]
    if tuple(e['ordinal'] for e in entries)!=ORDINALS:reject('pilot-coverage-mismatch')
    unit_ids={e['id'] for e in entries};segments=[s for s in inventory['structuralSegments'] if s['ownerUnitId'] in unit_ids]
    records={r['sourceUnitId']:r for r in audit['records'] if r['sourceUnitId'] in unit_ids}
    if len(records)!=13:reject('pilot-crosswalk-mismatch')
    for entry in entries:
        r=records[entry['id']]
        if r['sourceOrdinal']!=entry['ordinal'] or r['printedSourceNumber']!=entry['printedEntryNumber'] or r['authorityUnitRawSha256']!=entry['rawSha256']:reject('pilot-crosswalk-mismatch')
    result={'schema':'al-isabah.knowledge-pilot-preparation.v1','issue':89,'status':'prepared_not_executed','realExecutionEnabled':False,'realAdmissionEnabled':False,'ownerDecisionStatus':'not_recorded','methodRegistrySha256':digest(read(REGISTRY)),'inventoryFileSha256':PINS[INVENTORY.name],'auditFileSha256':PINS[AUDIT.name],'authority':{'sourceId':inventory['authority']['sourceId'],'artifactSha256':inventory['authority']['artifactSha256'],'revisionCommit':inventory['authority']['revision']['commit']},'candidateManifestSha256':audit['manifestSha256'],'sourceOrdinals':list(ORDINALS),'entries':entries,'structuralSegments':segments,'reusableCandidateEvidence':[records[e['id']] for e in entries],'counts':{'entries':len(entries),'structuralUnits':len(segments),'substantiveUnits':len(entries)+len(segments),'retainedFindings':sum(records[e['id']]['unresolvedCount'] for e in entries)},'spanPartitionStatus':'not_started','structuralCrosswalkStatus':'not_started','knowledgeExtractionStatus':'not_started','independentReviewStatus':'not_started','adjudicationStatus':'not_started','semanticIdentityReview':'not_started','translationFidelityReview':'not_started','rightsBasis':'existing_approved_source_limits_retained','artifactAdmission':'not_approved','preparationSha256':''}
    result['preparationSha256']=digest({k:v for k,v in result.items() if k!='preparationSha256'})
    if boundary_errors(result):reject('pilot-boundary-mismatch')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');args=p.parse_args()
    try:
        value=build();data=canonical(value)
        if args.check:
            if OUTPUT.read_bytes()!=data:reject('pilot-output-drift')
        else:OUTPUT.write_bytes(data)
        print(value['counts']);print(value['preparationSha256']);return 0
    except (Rejection,OSError) as error:
        print(str(error) if isinstance(error,Rejection) else 'pilot-io-error');return 1

if __name__=='__main__':raise SystemExit(main())
