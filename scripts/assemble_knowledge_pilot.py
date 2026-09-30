#!/usr/bin/env python3
"""Assemble ignored local knowledge-trial inputs and public-safe partition pins."""
import argparse
import hashlib
import re
from pathlib import Path
import translation_workflow as workflow
from knowledge_export import canonical,digest,read,reject,Rejection
import prepare_knowledge_pilot as preparation
from public_boundary import boundary_errors
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_PACKET=ROOT/'.runtime/knowledge/issue-0089/pilot-input.v1.json'
DEFAULT_METADATA=ROOT/'evidence/inventories/issue-0089-knowledge-pilot-partition.v1.json'
POLICIES=('docs/contracts/translation-quality-workflow.md','docs/translation-profiles/al-isabah.md','docs/contracts/entry-title-structure.md','docs/contracts/al-isabah-knowledge-export-v2-draft2.md')


def sha(raw):return hashlib.sha256(raw).hexdigest()

def lf_sha(path):return sha(path.read_text(encoding='utf-8-sig').replace('\r\n','\n').encode('utf-8'))


def partition_unit(unit_id,raw):
    """Split only at explicit OpenITI paragraph markers; never infer sentences/titles."""
    blocks=[];current=[]
    for line in raw.splitlines(keepends=True):
        if current and re.match(r'^(?:###|# )',line):blocks.append(''.join(current));current=[]
        current.append(line)
    if current:blocks.append(''.join(current))
    if ''.join(blocks)!=raw or not blocks:reject('pilot-partition-loss')
    return [{'id':'urn:al-isabah:trial:span:'+unit_id+':'+str(n),'sourceUnitId':unit_id,'partIndex':n,'sha256':sha(block.encode('utf-8')),'rawOpeniti':block} for n,block in enumerate(blocks,1)]


def assemble(source,candidate_root):
    prep=preparation.build();inventory=read(preparation.INVENTORY)
    if sha(source.read_bytes())!=prep['authority']['artifactSha256']:reject('pilot-source-pin-mismatch')
    root=candidate_root.resolve();manifest=read(root/'manifest.json')
    if sha((root/'manifest.json').read_bytes())!=prep['candidateManifestSha256']:reject('pilot-candidate-manifest-mismatch')
    pins={x['path']:x for x in manifest['files']}
    entries=workflow.parse_openiti_entries(source)
    if workflow.canonical_text_sha256(Path(workflow.__file__))!=inventory['parserLfSha256']:reject('pilot-parser-pin-mismatch')
    selected=set(prep['sourceOrdinals']);owned_ids={e['id'] for e in prep['entries']}|{s['id'] for s in prep['structuralSegments']}
    declared={e['id']:e for e in prep['entries']+prep['structuralSegments']}
    known_structures={x['id']:x for x in inventory['structuralSegments']}
    evidence={x['sourceOrdinal']:x for x in prep['reusableCandidateEvidence']}
    units=[];records=[];contexts={};active=[]
    for entry in entries:
        for heading in entry['precedingSegments']:
            if heading['kind']=='structural_heading':
                active=[s for s in active if s['headingLevel']<heading['headingLevel']]+[heading]
        ordinal=entry['sourceOrdinal']
        if ordinal not in selected:continue
        unit_id=entry['sourceUnitId'];record_id='urn:al-isabah:trial:source-record:'+evidence[ordinal]['legacyRecordId']
        for fragment in entry['precedingSegments']+[entry]:
            identity=fragment.get('segmentId',fragment.get('sourceUnitId'))
            if identity not in declared or declared[identity]['rawSha256']!=fragment['rawSha256'] or sha(fragment['rawOpeniti'].encode('utf-8'))!=fragment['rawSha256']:reject('pilot-unit-pin-mismatch')
            units.append({'id':identity,'kind':fragment.get('kind','entry'),'sourceRecordVersionId':record_id,'rawSha256':fragment['rawSha256'],'spans':partition_unit(identity,fragment['rawOpeniti'])})
        context_ids=[]
        for heading in active:
            identity=heading['segmentId'];context_ids.append(identity)
            if identity in owned_ids:continue
            if identity not in known_structures or known_structures[identity]['rawSha256']!=heading['rawSha256']:reject('pilot-context-pin-mismatch')
            contexts[identity]={'id':identity,'kind':'inherited_heading_context','headingLevel':heading['headingLevel'],'rawSha256':heading['rawSha256'],'rawOpeniti':heading['rawOpeniti']}
        old=evidence[ordinal];member='items/'+old['legacyRecordId']+'.json';path=root/member
        if path.is_symlink() or not path.resolve().is_relative_to(root):reject('pilot-candidate-member-invalid')
        raw=path.read_bytes()
        if member not in pins or sha(raw)!=old['candidateRecordSha256'] or sha(raw)!=pins[member]['sha256'] or len(raw)!=pins[member]['bytes']:reject('pilot-candidate-member-mismatch')
        candidate=read(path)
        if candidate['id']!=old['legacyRecordId'] or candidate['sourceEntryNumber']!=entry['sourceEntryNumber'] or candidate['source']['license']['spdx']!='CC-BY-NC-SA-4.0' or candidate['publicEligibility']!='eligible':reject('pilot-candidate-identity-mismatch')
        records.append({'id':record_id,'legacyRecordId':old['legacyRecordId'],'sourceOrdinal':ordinal,'sourceUnitId':unit_id,'sourceUnitIds':[s['segmentId'] for s in entry['precedingSegments']]+[unit_id],'inheritedContextUnitIds':context_ids,'candidateRecordSha256':old['candidateRecordSha256'],'candidateEnglish':{'title':candidate['title']['en'],'segments':[{'id':s['id'],'english':s['english']} for s in candidate['segments']]},'retainedFindings':candidate['unresolved'],'priorMachineAssessment':candidate['machineAssessment'],'humanReview':'unreviewed'})
    if {u['id'] for u in units}!=owned_ids or len(records)!=13:reject('pilot-assembly-coverage-mismatch')
    packet={'schema':'al-isabah.knowledge-pilot-input.v1','issue':89,'status':'prepared_not_executed','preparationSha256':prep['preparationSha256'],'inventoryFileSha256':prep['inventoryFileSha256'],'auditFileSha256':prep['auditFileSha256'],'sourceArtifactSha256':prep['authority']['artifactSha256'],'candidateManifestSha256':prep['candidateManifestSha256'],'methodRegistrySha256':prep['methodRegistrySha256'],'parserLfSha256':inventory['parserLfSha256'],'assemblerLfSha256':lf_sha(Path(__file__)),'policyPins':{p:lf_sha(ROOT/p) for p in POLICIES},'records':records,'units':units,'inheritedContextUnits':sorted(contexts.values(),key=lambda x:x['id']),'rights':{'license':'CC-BY-NC-SA-4.0','basis':'existing_approved_source_and_verified_successor','publicReleaseApproved':False},'packetSha256':''}
    packet['packetSha256']=digest({k:v for k,v in packet.items() if k!='packetSha256'})
    metadata={'schema':'al-isabah.knowledge-pilot-partition.v1','issue':89,'status':'deterministically_prepared_not_semantically_reviewed','packetSha256':packet['packetSha256'],'packetFileSha256':digest(packet),'preparationSha256':prep['preparationSha256'],'inventoryFileSha256':prep['inventoryFileSha256'],'methodRegistrySha256':prep['methodRegistrySha256'],'assemblerLfSha256':packet['assemblerLfSha256'],'parserLfSha256':packet['parserLfSha256'],'sourceOrdinals':list(preparation.ORDINALS),'records':[{'id':r['id'],'legacyRecordId':r['legacyRecordId'],'sourceOrdinal':r['sourceOrdinal'],'sourceUnitIds':r['sourceUnitIds'],'inheritedContextUnitIds':r['inheritedContextUnitIds'],'candidateRecordSha256':r['candidateRecordSha256'],'retainedFindingCount':len(r['retainedFindings'])} for r in records],'units':[{'id':u['id'],'kind':u['kind'],'sourceRecordVersionId':u['sourceRecordVersionId'],'rawSha256':u['rawSha256'],'spans':[{k:v for k,v in s.items() if k!='rawOpeniti'} for s in u['spans']]} for u in units],'inheritedContextUnits':[{k:v for k,v in c.items() if k!='rawOpeniti'} for c in packet['inheritedContextUnits']],'counts':{**prep['counts'],'spans':sum(len(u['spans']) for u in units),'inheritedContextUnits':len(contexts)},'knowledgeExtractionStatus':'not_started','structuralEnglishAlignmentStatus':'not_started','realExecutionAuthorized':False,'publicReleaseAuthorized':False,'partitionSha256':''}
    metadata['partitionSha256']=digest({k:v for k,v in metadata.items() if k!='partitionSha256'})
    if boundary_errors(metadata):reject('pilot-metadata-boundary-mismatch')
    return packet,metadata


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--candidate-root',required=True,type=Path);p.add_argument('--check',action='store_true');a=p.parse_args()
    try:
        packet,metadata=assemble(a.source,a.candidate_root)
        if a.check:
            if DEFAULT_PACKET.read_bytes()!=canonical(packet) or DEFAULT_METADATA.read_bytes()!=canonical(metadata):reject('pilot-assembly-drift')
        else:
            DEFAULT_PACKET.parent.mkdir(parents=True,exist_ok=True)
            for path,value in [(DEFAULT_PACKET,packet),(DEFAULT_METADATA,metadata)]:
                if path.exists() and path.read_bytes()!=canonical(value):reject('pilot-existing-output-conflict')
                if not path.exists():
                    with path.open('xb') as stream:stream.write(canonical(value))
        print(metadata['counts']);print('packet',packet['packetSha256']);print('partition',metadata['partitionSha256']);return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError):print('pilot-assembly-failed');return 1

if __name__=='__main__':raise SystemExit(main())
