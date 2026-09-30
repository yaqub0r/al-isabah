"""Additive local.1 projection of a verified gated lineage; no admission."""
import copy

import knowledge_export_v2_draft3 as graph
import knowledge_local_gated_history_v1 as replay
import knowledge_local_projection as prior_projection
import knowledge_pilot_trial as old
from knowledge_export import canonical,digest,read,reject
from knowledge_local_schema import VERSION

PROJECTION_VERSION='al-isabah.local-gated-stage-projection.v1'


def projection_code_digest():
    return digest({'version':PROJECTION_VERSION,'baseProjectionCodeSha256':prior_projection.projection_code_digest(),
                   'adapterLfSha256':old.assembly.lf_sha(old.ROOT/'scripts/knowledge_local_gated_projection_v1.py'),
                   'replayLfSha256':old.assembly.lf_sha(old.ROOT/'scripts/knowledge_local_gated_history_v1.py')})


def identity(kind,value):
    return 'urn:al-isabah:local:'+kind+':'+digest({'value':value,'version':PROJECTION_VERSION,
                                                   'code':projection_code_digest()})[:32]


def bind_finding_source_owners(stage,packet,known_prior=None):
    """Expose source ownership already implied by each projected finding target."""
    known_prior=known_prior or {}
    maps={kind:{row['id']:row for row in stage[kind]} for kind in graph.COLLECTIONS}
    spans={s['id']:u['sourceRecordVersionId'] for u in packet['units'] for s in u['spans']}
    for finding in stage['findings']:
        prior=known_prior.get(finding['id'])
        if prior is not None and finding==prior:continue
        owners=set()
        for target in finding['targets']:
            kind=target['kind'];ref=target['id']
            if kind=='sourceRecords':owners.add(ref);continue
            if kind=='sourceSpans':
                if ref not in spans:reject('gated-finding-owner-unresolved')
                owners.add(spans[ref]);continue
            obj=maps.get(kind,{}).get(ref)
            if obj is None:reject('gated-finding-owner-unresolved')
            found=set(obj.get('sourceRecordVersionIds',[]))
            if 'sourceRecordVersionId' in obj:found.add(obj['sourceRecordVersionId'])
            if 'sourceSpanId' in obj:found.add(spans[obj['sourceSpanId']])
            if not found:reject('gated-finding-owner-unresolved')
            owners.update(found)
        if not owners:reject('gated-finding-owner-unresolved')
        existing={t['id'] for t in finding['targets'] if t['kind']=='sourceRecords'}
        finding['targets'].extend({'kind':'sourceRecords','id':rid} for rid in sorted(owners-existing))
        if prior is not None and finding!=prior:reject('gated-finding-prior-identity-conflict')


def project_history(history,pins,requested,prior_bundle=None):
    normalized=replay.validate_history(history,pins);packet=normalized['packet']
    profile=prior_projection.profile_value()
    inventory,source_records=prior_projection.inventory_value(packet,profile,requested)
    classifications=prior_projection.baseline_classifications(normalized['baseline'],packet,
        read(prior_projection.BASELINE_CLASSIFICATIONS),prior_projection.BASELINE_CLASSIFICATIONS_SHA256)
    stages=[prior_projection.stage_snapshot(item,packet,inventory,source_records,profile,n,classifications)
            for n,item in enumerate(normalized['stages'])]
    previous=None
    if prior_bundle is not None:
        if prior_bundle.get('projectionVersion')==PROJECTION_VERSION:
            previous=project_history(prior_bundle['history'],prior_bundle['pins'],
                                     prior_bundle['requestedSourceRecordVersionIds'],prior_bundle.get('priorBundle'))
        else:
            previous=prior_projection.project_history(prior_bundle['history'],
                       prior_bundle['requestedSourceRecordVersionIds'],prior_bundle.get('priorBundle'))
        if previous[3]!=prior_bundle:reject('gated-prior-projection-binding-mismatch')
        if previous[1]!=inventory or previous[2]!=profile:reject('gated-cumulative-projection-context-mismatch')
    known={x['id']:x for x in previous[0]['findings']} if previous else {}
    for stage in stages:bind_finding_source_owners(stage,packet,known)
    result=copy.deepcopy(stages[-1]);final={(kind,v['id']) for kind in graph.COLLECTIONS for v in result[kind]}
    if previous is not None:
        for kind in graph.COLLECTIONS:prior_projection.merge_objects(result[kind],previous[0][kind])
    for stage in stages[:-1]:
        for kind in graph.COLLECTIONS:prior_projection.merge_objects(result[kind],stage[kind])
    decision_artifact=identity('adjudication-proposal',normalized['stages'][-1]['proposal'])
    result['artifacts'].append({'id':decision_artifact,'kind':'review_decision',
                                'sha256':digest(normalized['stages'][-1]['proposal']),'status':'proposed'})
    code=projection_code_digest();method=identity('gated-projection-method',code)
    result['artifacts'].append({'id':method,'kind':'method','sha256':code,'status':'proposed'})
    already_retired={(r['kind'],r['id']) for event in result['lifecycleEvents'] for r in event['targets']}
    for kind in (*old.COLLECTIONS,'spanDispositions'):
        for value in result[kind]:
            if (kind,value['id']) not in final and (kind,value['id']) not in already_retired:
                result['lifecycleEvents'].append({'id':identity('stage-retirement',[kind,value['id'],decision_artifact]),
                    'kind':'withdraws','targets':[{'kind':kind,'id':value['id']}],'replacements':[],
                    'decisionArtifactId':decision_artifact,'effectiveAt':prior_projection.unknown(),
                    'dependencyIds':[]})
    receipt_ids=[identity('exporter-derived-receipt',[digest(x['receipt']),digest(inventory),digest(profile),requested,
                                                  normalized['lineageSha256']]) for x in normalized['stages']]
    dependencies=sorted(r['id'] for r in source_records if r['id'] not in requested)
    bundle={'schema':'al-isabah.knowledge-local-receipt-bundle.v1','projectionVersion':PROJECTION_VERSION,
            'derivedBy':'exporter','history':copy.deepcopy(history),'pins':copy.deepcopy(pins),
            'lineageSha256':normalized['lineageSha256'],'requestedSourceRecordVersionIds':requested,
            'dependencySourceRecordVersionIds':dependencies,
            'receipts':copy.deepcopy(prior_bundle['receipts']) if prior_bundle else [],
            'bindings':copy.deepcopy(prior_bundle['bindings']) if prior_bundle else [],
            'completionDerivation':[prior_projection.completion_evidence(normalized['stages'][-1]['proposal']['output'],
                packet,r['id'],[v for v in stages[-1]['spanDispositions'] if v['sourceRecordVersionId']==r['id']],classifications)
                for r in source_records]}
    if prior_bundle is not None:bundle['priorBundle']=copy.deepcopy(prior_bundle)
    derived_chain=[]
    for n,(item,stage) in enumerate(zip(normalized['stages'],stages)):
        # The final receipt attests the cumulative active snapshot. Earlier
        # withdrawn objects remain separately bound by lifecycle events.
        outputs=graph.semantic_projection(result if n==len(stages)-1 else stage,requested,dependencies)
        inputs={'inventorySha256':digest(inventory),'profileSha256':digest(profile),
                'sourceRecords':[{'id':r['id'],'sha256':digest(r)} for r in sorted(source_records,key=lambda x:x['id'])],
                'requestedSourceRecordVersionIds':requested,'dependencySourceRecordVersionIds':dependencies,
                'upstreamOutputSha256':derived_chain[-1]['outputSha256'] if n else ''}
        receipt={'schema':PROJECTION_VERSION,'id':receipt_ids[n],'derivedBy':'exporter','stage':old.STAGES[n],
                 'projectionCodeSha256':code,'sourceReceiptSha256':digest(item['receipt']),
                 'sourceProposalSha256':digest(item['proposal']),
                 'sourceDecisionSha256':normalized['stageDecisionSha256'][n],
                 'sourceLineageSha256':normalized['lineageSha256'],
                 'sourceRecordVersionIds':sorted(r['id'] for r in source_records),
                 'inputSha256':digest(inputs),'outputSha256':digest(outputs),
                 'upstreamReceiptIds':receipt_ids[n-1:n]}
        derived_chain.append(receipt);prior_projection.merge_objects(bundle['receipts'],[receipt])
        binding={'receiptId':receipt_ids[n],'inputs':inputs,'outputs':outputs}
        prior_binding=next((b for b in bundle['bindings'] if b['receiptId']==receipt_ids[n]),None)
        if prior_binding is not None and prior_binding!=binding:reject('immutable-id-conflict')
        if prior_binding is None:bundle['bindings'].append(binding)
        result['artifacts'].append({'id':receipt_ids[n],'kind':'knowledge_receipt','sha256':digest(receipt),'status':'proposed'})
    actor=prior_projection.identity('exporter-actor',prior_projection.PROJECTION_VERSION)
    not_performed=prior_projection.identity('not-performed-actor',prior_projection.PROJECTION_VERSION)
    old_method=prior_projection.identity('method',[prior_projection.PROJECTION_VERSION,
                                                    prior_projection.projection_code_digest()])
    maps={key:graph.indexed(result[key]) for key in graph.COLLECTIONS};result['assessmentSelection']=[]
    for record in source_records:
        rid=record['id'];rows=[r for r in stages[-1]['spanDispositions'] if r['sourceRecordVersionId']==rid]
        targets=[{'kind':'sourceRecords','id':rid},*[{'kind':'spanDispositions','id':r['id']} for r in rows]]
        status=next(a['status'] for a in stages[-1]['assessments'] if a['kind']=='adjudication' and a['targets']==targets)
        eid=identity('extraction-summary',[digest(normalized['report']),rid,receipt_ids])
        hid=prior_projection.identity('human-unreviewed',[digest(record)])
        for aid,kind,state,who,refs,receipts in [(eid,'extraction',status,actor,targets,receipt_ids),
                                                  (hid,'human_review','unreviewed',not_performed,[targets[0]],[])]:
            result['assessments'].append({'id':aid,'kind':kind,'status':state,'actorId':who,
                'methodArtifactId':old_method if kind=='human_review' else method,'targets':refs,
                'inputs':[{'ref':r,'sha256':digest(maps[r['kind']][r['id']])} for r in refs],
                'effectiveAt':prior_projection.unknown(kind!='human_review'),
                'observedAt':prior_projection.unknown(kind!='human_review'),
                'predecessorIds':[],'findingIds':[],'receiptArtifactIds':receipts})
        result['assessmentSelection'].append({'sourceRecordVersionId':rid,'extractionAssessmentId':eid,
                                              'humanReviewAssessmentId':hid})
    stamp=digest({'reportSha256':digest(normalized['report']),'lineageSha256':normalized['lineageSha256'],
                  'priorBundleSha256':digest(prior_bundle) if prior_bundle else ''})
    result.update(schemaId='al-isabah.knowledge-snapshot.v2-local1',id=identity('snapshot',[stamp,requested]),
                  schemaVersion=VERSION,mode='real',fixtureClass='not-a-fixture',admissionClass='local_provisional',
                  authority=copy.deepcopy(profile['authority']),inventorySha256=digest(inventory),
                  profileSha256=digest(profile),receiptBundleSha256=digest(bundle),
                  batch={'id':identity('batch',[stamp,requested]),'exportId':identity('export',[stamp,requested]),
                         'selectionMode':'full_snapshot',
                         'requestedLogicalRecordIds':sorted(r['id'] for r in inventory['logicalRecords'] if r['inScope']),
                         'dependencyLogicalRecordIds':sorted(r['id'] for r in inventory['logicalRecords'] if not r['inScope'])})
    for kind in graph.COLLECTIONS:
        unique=[]
        try:prior_projection.merge_objects(unique,result[kind])
        except graph.Rejection:reject('gated-projection-immutable-conflict-'+kind)
        result[kind]=sorted(unique,key=lambda x:x['id'])
    for kind in ('currentSourceSelection','currentSpanDispositionSelection','assessmentSelection'):
        result[kind].sort(key=canonical)
    return result,inventory,profile,bundle


def validate_projection(snapshot,inventory,profile,bundle):
    expected=project_history(bundle['history'],bundle['pins'],bundle['requestedSourceRecordVersionIds'],
                             bundle.get('priorBundle'))
    if (snapshot,inventory,profile,bundle)!=expected:reject('gated-projection-binding-mismatch')
    return {r['id']:r for r in bundle['receipts']}
