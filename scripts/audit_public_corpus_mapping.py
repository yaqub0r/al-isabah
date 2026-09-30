#!/usr/bin/env python3
"""Read-only candidate mapping/hash audit; output contains no source expression."""
import argparse
import collections
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from knowledge_export import canonical, digest, read

ENTRY = re.compile(r'^### \$+\s+(\d+)\s+(.*)$')

def sha(raw):return hashlib.sha256(raw).hexdigest()

def legacy_exact_domains(source):
    """Historical projection domain: omit heading lines, preserve other lines.

    This deliberately differs from the current entry+structural parser. It is
    used only to verify old hashes, never to define new source coverage.
    """
    entries={}; number=None; lines=[]
    def flush():
        if number is not None:
            entries.setdefault(number,[]).append(sha('\n'.join(lines).encode('utf-8')))
    for line in source.read_text(encoding='utf-8').splitlines():
        match=ENTRY.match(line)
        if match:
            flush();number=int(match.group(1));lines=[line]
        elif number is not None and not (line.startswith('### ') and not line.startswith('### $')):
            lines.append(line)
    flush();return entries


def audit(root, source, inventory_path, expected_manifest_sha, expected_inventory_sha, legacy_ids=None):
    inventory_bytes=inventory_path.read_bytes()
    if sha(inventory_bytes)!=expected_inventory_sha:raise ValueError('inventory-pin-mismatch')
    inventory=json.loads(inventory_bytes)
    if digest({k:v for k,v in inventory.items() if k!='inventorySha256'})!=inventory['inventorySha256']:raise ValueError('inventory-content-mismatch')
    root=root.resolve()
    manifest_bytes=(root/'manifest.json').read_bytes()
    if sha(manifest_bytes)!=expected_manifest_sha:raise ValueError('manifest-pin-mismatch')
    manifest=json.loads(manifest_bytes)
    authority=inventory['authority']['artifactSha256']
    if sha(source.read_bytes())!=authority or manifest['sourceArtifactSha256']!=authority:raise ValueError('source-pin-mismatch')
    pins={}; file_count=0
    for item in manifest['files']:
        rel=PurePosixPath(item['path'])
        if rel.is_absolute() or '..' in rel.parts or '\\' in item['path'] or ':' in item['path']:raise ValueError('unsafe-manifest-member')
        path=root.joinpath(*rel.parts)
        if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('unsafe-manifest-member')
        if item['path'] in pins:raise ValueError('duplicate-manifest-member')
        raw=path.read_bytes()
        if len(raw)!=item['bytes'] or sha(raw)!=item['sha256']:raise ValueError('manifest-member-mismatch')
        pins[item['path']]=item['sha256'];file_count+=1
    if file_count!=manifest['objectCount']:raise ValueError('manifest-count-mismatch')
    index=read(root/'index.json'); summary=read(root/'summary.json')
    if any(name not in pins for name in ['index.json','summary.json','exclusions.json','quarantine.json']):raise ValueError('manifest-metadata-missing')
    if index['corpusId']!=manifest['corpusId'] or summary['corpus']['id']!=manifest['corpusId']:raise ValueError('corpus-identity-mismatch')
    exact=legacy_exact_domains(source)
    expected={e['printedEntryNumber']:e for e in inventory['entries']}
    if len(expected)!=len(inventory['entries']):raise ValueError('ambiguous-source-number')
    allocated=legacy_ids if legacy_ids is not None else {f'isabah-entry-{n:08d}' for n in range(10759,12309)}
    selected=[x for x in index['items'] if x['id'] in allocated]
    if {x['id'] for x in selected}!=allocated or len(selected)!=len(allocated):raise ValueError('legacy-id-coverage-mismatch')
    records=[]; statuses=collections.Counter(); findings=collections.Counter(); headings=0; names=0; source_numbers=[]
    for row in selected:
        rid=row['id']; member='items/'+rid+'.json'
        if member not in pins:raise ValueError('item-unbound')
        item=read(root/member); n=item['sourceEntryNumber']; source_numbers.append(n)
        if item['id']!=rid or n!=row['sourceEntryNumber'] or n not in expected:raise ValueError('mapping-mismatch')
        if item['remediation']['legacyAllocationNumber']!=int(rid.rsplit('-',1)[1]):raise ValueError('legacy-allocation-mismatch')
        declared=item['source']['sourceExactTextSha256']
        if exact.get(n)!=[declared]:raise ValueError('exact-source-domain-mismatch')
        displayed=' '.join((item['title']['ar']+' '+' '.join(s['arabic'] for s in item['segments'])).split())
        if sha(displayed.encode('utf-8'))!=item['source']['sourceTextSha256']:raise ValueError('display-domain-mismatch')
        if item['provenance']['sourceArtifactSha256']!=authority or item['provenance']['sourceExactTextSha256']!=declared:raise ValueError('provenance-mismatch')
        if item['source']['license']['spdx']!='CC-BY-NC-SA-4.0':raise ValueError('license-label-mismatch')
        for key in ['machineAssessment','humanReview','publicEligibility','translationState']:
            if item[key]!=row[key]:raise ValueError('index-state-mismatch')
        if row['unresolvedCount']!=len(item['unresolved']):raise ValueError('finding-count-mismatch')
        for finding in item['unresolved']:
            category=finding.get('category','unknown');priority=finding.get('priority','unknown')
            if not re.fullmatch('[a-z_-]+',category) or not re.fullmatch('[a-z_-]+',priority):raise ValueError('unsafe-finding-code')
            findings[(category,priority)]+=1
        headings+=len(item['headingsBefore']);names+=len(item['names']);statuses[item['machineAssessment']]+=1
        records.append({'legacyRecordId':rid,'sourceUnitId':expected[n]['id'],'sourceOrdinal':expected[n]['ordinal'],'printedSourceNumber':n,'candidateRecordSha256':pins[member],'historicalExactSourceSha256':declared,'authorityUnitRawSha256':expected[n]['rawSha256'],'candidateDisplaySha256':item['source']['sourceTextSha256'],'machineAssessment':item['machineAssessment'],'humanReview':item['humanReview'],'candidatePublicEligibility':item['publicEligibility'],'unresolvedCount':len(item['unresolved']),'findingDispositions':[{'category':f['category'],'priority':f['priority']} for f in item['unresolved']]})
    if len(set(source_numbers))!=len(expected) or set(source_numbers)!=set(expected):raise ValueError('source-coverage-mismatch')
    report={'schema':'al-isabah.candidate-crosswalk-audit.v1','status':'candidate-declared-mapping-and-byte-domains-verified-not-semantic-or-admission-approval','candidateCorpusId':manifest['corpusId'],'manifestSha256':expected_manifest_sha,'metadataSha256':{key.split('.')[0]:pins[key] for key in ['index.json','summary.json','exclusions.json','quarantine.json']},'sourceArtifactSha256':authority,'selectedInventorySha256':inventory['inventorySha256'],'selectedInventoryFileSha256':expected_inventory_sha,'verifiedManifestMembers':file_count,'sourceEntryCount':len(expected),'legacyRecordCount':len(records),'machineAssessments':dict(statuses),'unresolvedItems':sum(findings.values()),'findingDispositions':[{'category':cat,'priority':pri,'count':count} for (cat,pri),count in sorted(findings.items())],'candidateHeadingsBeforeCount':headings,'expectedStructuralSegmentCount':len(inventory['structuralSegments']),'candidateNameRecords':names,'semanticIdentityReview':'not_performed','translationFidelityReview':'not_performed','rightsAdmission':'not_approved_by_this_audit','records':sorted(records,key=lambda x:x['legacyRecordId'])}
    report['auditSha256']=digest(report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['candidate-root','source','inventory','output']:p.add_argument('--'+key,required=True,type=Path)
    p.add_argument('--manifest-sha256',required=True);p.add_argument('--inventory-sha256',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
    try:
        value=audit(a.candidate_root,a.source,a.inventory,a.manifest_sha256,a.inventory_sha256);raw=canonical(value)
        if a.check:
            if a.output.read_bytes()!=raw:raise ValueError('audit-byte-mismatch')
        else:
            a.output.parent.mkdir(exist_ok=True,parents=True)
            with a.output.open('xb') as f:f.write(raw)
        print(json.dumps({k:value[k] for k in ['candidateCorpusId','verifiedManifestMembers','sourceEntryCount','legacyRecordCount','machineAssessments','unresolvedItems','candidateHeadingsBeforeCount','expectedStructuralSegmentCount','candidateNameRecords','auditSha256']}));return 0
    except (ValueError,OSError,KeyError,TypeError):print('candidate-audit-failed');return 1

if __name__=='__main__':raise SystemExit(main())
