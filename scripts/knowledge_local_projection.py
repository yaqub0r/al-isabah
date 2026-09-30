"""Deterministic rich projection of preserved stages; generated receipts are exporter-derived."""
import copy
import knowledge_export_v2_draft3 as graph
import knowledge_pilot_trial as old
from knowledge_export import digest,read,reject
from knowledge_local_schema import VERSION
from knowledge_local_execution import validate_history

PROJECTION_VERSION='al-isabah.local-stage-projection.v1'
BASELINE_CLASSIFICATIONS=old.ROOT/'profiles/knowledge/local-baseline-provenance.v1.json'
BASELINE_CLASSIFICATIONS_SHA256='a849fb1a3fccd9ac8fad1a9510225574ba76680b85eab42d1d6b6c232118277d'


def projection_code_digest():
    paths=['scripts/knowledge_local_projection.py','scripts/knowledge_local_execution.py','scripts/knowledge_local_semantics.py',
           'scripts/knowledge_export_local.py','scripts/knowledge_local_authorization.py','scripts/knowledge_local_schema.py',
           'schemas/al-isabah-knowledge-export.v2-local1.schema.json','profiles/knowledge/local-execution-verifier.v1.json',
           'profiles/knowledge/local-baseline-provenance.v1.json']
    return digest({'domain':'al-isabah.local-exporter-code.v1','files':[
        {'path':path,'lfSha256':old.assembly.lf_sha(old.ROOT/path)} for path in paths]})


def identity(kind,value,versioned=True):
    binding={'value':value,'projectionVersion':PROJECTION_VERSION,'projectionCodeSha256':projection_code_digest()} if versioned else value
    return 'urn:al-isabah:local:'+kind+':'+digest(binding)[:32]
def unknown(performed=True):return {'status':'unknown','timestamp':'','reasonCode':'not_recorded' if performed else 'not_performed'}
def profile_value():
    value=copy.deepcopy(read(old.ROOT/'profiles/knowledge/volume-08.v2-draft3.json'))
    value.update(schemaId='al-isabah.knowledge-profile.v2-local1',id='urn:al-isabah:profile:knowledge-local1',version=VERSION,
                 status='local_provisional',realExecutionEnabled=False,realAdmissionEnabled=True)
    value['rights'].update(basis='cc_by_nc_sa_4_0',approvalStatus='requires_exact_local_authorization')
    return value


def source_record_binding(packet,record,profile):
    owned=set(record['sourceUnitIds']);context_ids=record.get('inheritedContextUnitIds',[])
    units={u['id']:u for u in packet['units']}
    contexts={u['id']:u for u in packet.get('inheritedContextUnits',[])}
    def metadata(unit):
        return {k:copy.deepcopy(v) for k,v in unit.items() if k not in {'rawOpeniti','spans','sourceRecordVersionId'}}
    source_units=[]
    for uid in sorted(owned):
        unit=units[uid]
        source_units.append({**metadata(unit),'spans':[{k:v for k,v in span.items() if k!='rawOpeniti'} for span in unit['spans']]})
    context=[]
    for uid in sorted(context_ids):
        if uid not in contexts and uid not in units:reject('local-projection-context-missing')
        context.append(metadata(contexts[uid] if uid in contexts else units[uid]))
    return {'authority':profile['authority'],'sourceOrdinal':record['sourceOrdinal'],'sourceUnits':source_units,'inheritedContext':context}


def baseline_classifications(baseline,packet,mapping,expected_pin):
    if digest(mapping)!=expected_pin:reject('local-baseline-classification-mismatch')
    original=baseline['stages'][-1]['output']
    if digest(original)!=mapping['baselineOutputSha256']:return {}
    concerns=graph.indexed(original['concerns']);ledger={r['id']:r for r in old.retained_ledger(packet)}
    coverage={r['sourceFindingId']:r for r in original['retainedFindingCoverage']}
    result={}
    for row in mapping['entries']:
        cid=row['baselineConcernId'];fid=row['sourceFindingId'];concern=concerns.get(cid);finding=ledger.get(fid)
        if (cid in result or not concern or not finding or digest(concern)!=row['baselineConcernSha256']
            or finding['evidenceSha256']!=row['sourceFindingEvidenceSha256'] or finding['sourceRecordVersionId']!=row['sourceRecordVersionId']
            or finding['evidence'].get('category')!='legacy-review-finding' or concern['sourceSpanIds']!=row['sourceSpanIds']
            or cid not in coverage.get(fid,{}).get('concernIds',[])):reject('local-baseline-classification-mismatch')
        owners={s['id']:u['sourceRecordVersionId'] for u in packet['units'] for s in u['spans']}
        if any(owners.get(sid)!=row['sourceRecordVersionId'] for sid in row['sourceSpanIds']):reject('local-baseline-classification-mismatch')
        result[cid]={'binding':row,'originalConcern':concern}
    return result


def completion_evidence(output,packet,rid,rows,classifications=None):
    classifications=classifications or {}
    owners={s['id']:u['sourceRecordVersionId'] for u in packet['units'] for s in u['spans']}
    ledger={row['id']:row for row in old.retained_ledger(packet)}
    coverage={c['id']:[] for c in output['concerns']}
    for row in output['retainedFindingCoverage']:
        for cid in row['concernIds']:coverage[cid].append(ledger[row['sourceFindingId']])
    substantive=[];inherited=[]
    for concern in output['concerns']:
        if concern['status']!='open' or not any(owners[s]==rid for s in concern['sourceSpanIds']):continue
        evidence=coverage[concern['id']]
        classified=classifications.get(concern['id'])
        if classified and not any(x['id']==classified['binding']['sourceFindingId'] for x in evidence):reject('local-baseline-classification-mismatch')
        generic=bool(classified) and concern==classified['originalConcern'] and bool(evidence) and all(x['evidence'].get('category')=='legacy-review-finding' for x in evidence)
        (inherited if generic else substantive).append(concern['id'])
    maps={key:graph.indexed(output[key]) for key in old.COLLECTIONS};blocking=[]
    for finding in output['findings']:
        if finding['severity']!='blocking' or finding['disposition']!='unresolved':continue
        affected=set()
        for ref in finding['targets']:
            if ref['kind']=='sourceRecords':affected.add(ref['id']);continue
            if ref['kind']=='sourceSpans':affected.add(owners[ref['id']]);continue
            obj=maps.get(ref['kind'],{}).get(ref['id'],{})
            affected.update(obj.get('sourceRecordVersionIds',[]))
            if 'sourceRecordVersionId' in obj:affected.add(obj['sourceRecordVersionId'])
            if 'sourceSpanId' in obj:affected.add(owners[obj['sourceSpanId']])
        if rid in affected or not affected:blocking.append(finding['id'])
    review=next(r for r in output['recordReviews'] if r['sourceRecordVersionId']==rid)
    complete=all(r['status'] not in graph.BLOCKED for r in rows) and all(review[k]=='checked' for k in old.REVIEW_AXES) and not substantive and not blocking
    return {'sourceRecordVersionId':rid,'status':'complete' if complete else 'partial',
            'substantiveOpenConcernIds':sorted(substantive),'inheritedProvenanceConcernIds':sorted(inherited),'blockingFindingIds':sorted(blocking)}


def inventory_value(packet,profile,requested):
    records={r['id']:r for r in packet['records']}
    if requested!=sorted(set(requested)) or not requested or not set(requested)<=set(records):reject('local-projection-scope-mismatch')
    unit_ids={u['id']:identity('unit',[profile['authority']['revisionId'],u['id']],versioned=False) for u in packet['units']}
    logical={rid:identity('logical-record',[profile['authority']['revisionId'],r['sourceOrdinal']],versioned=False) for rid,r in records.items()}
    inventory={'schemaId':'al-isabah.knowledge-inventory.v2-local1','id':identity('inventory',[packet['packetSha256'],requested]),
        'authority':copy.deepcopy(profile['authority']),'selectedScopeSha256':profile['selectedScopeSha256'],
        'reconciliationStatus':'fresh_derivation_legacy_mapping_unverified','reconciliationEvidenceSha256':packet['packetSha256'],
        'sourceUnits':[],'sourceSpans':[],'logicalRecords':[]}
    for rid,record in records.items():
        inventory['logicalRecords'].append({'id':logical[rid],'sourceUnitIds':[unit_ids[u] for u in record['sourceUnitIds']],'inScope':rid in requested})
    for unit in packet['units']:
        rid=unit['sourceRecordVersionId'];record=records[rid]
        entry=[u for u in packet['units'] if u['sourceRecordVersionId']==rid and u['kind']=='entry']
        if len(entry)!=1:reject('local-projection-owner-mismatch')
        inventory['sourceUnits'].append({'id':unit_ids[unit['id']],'kind':unit['kind'],'ownerEntryId':unit_ids[entry[0]['id']],
            'rawSha256':unit['rawSha256'],'locations':[],'inScope':rid in requested})
        inventory['sourceSpans'].extend({'id':s['id'],'sourceUnitId':unit_ids[unit['id']],'sha256':s['sha256']} for s in unit['spans'])
    for key in ('logicalRecords','sourceUnits','sourceSpans'):inventory[key].sort(key=lambda x:x['id'])
    source_records=[{'id':rid,'logicalRecordId':logical[rid],'authorityUnitIds':[unit_ids[u] for u in record['sourceUnitIds']],
                     'recordSha256':digest(source_record_binding(packet,record,profile)),'sourceArtifactId':'urn:al-isabah:trial:artifact:authority'} for rid,record in records.items()]
    return inventory,source_records


def merge_objects(target,values):
    known={v['id']:v for v in target}
    for value in values:
        if value['id'] in known and known[value['id']]!=value:reject('immutable-id-conflict')
        if value['id'] not in known:target.append(copy.deepcopy(value));known[value['id']]=value


def stage_snapshot(item,packet,inventory,source_records,profile,index,classifications=None):
    output=item['proposal']['output'];stamp=digest(item['proposal']);records={r['id']:r for r in packet['records']}
    owners={s['id']:u['sourceRecordVersionId'] for u in packet['units'] for s in u['spans']}
    value={key:copy.deepcopy(output[key]) if key in old.COLLECTIONS else [] for key in graph.COLLECTIONS}
    value['sourceRecords']=copy.deepcopy(source_records)
    method=identity('method',[PROJECTION_VERSION,projection_code_digest()]);authority=identity('actor-authority',PROJECTION_VERSION)
    actor=identity('exporter-actor',PROJECTION_VERSION);not_performed=identity('not-performed-actor',PROJECTION_VERSION)
    value['artifacts']=[{'id':'urn:al-isabah:trial:artifact:authority','kind':'source_derivation','sha256':packet['sourceArtifactSha256'],'status':'proposed'},
                        {'id':'urn:al-isabah:trial:artifact:candidate-manifest','kind':'source_derivation','sha256':packet['candidateManifestSha256'],'status':'proposed'},
                        {'id':method,'kind':'method','sha256':projection_code_digest(),'status':'proposed'},
                        {'id':authority,'kind':'actor_authority','sha256':digest({'actor':'deterministic_exporter','version':PROJECTION_VERSION}),'status':'proposed'}]
    value['actors']=[{'id':actor,'kind':'machine','authorityArtifactId':authority},{'id':not_performed,'kind':'not_performed','authorityArtifactId':authority}]
    for concern in output['concerns']:
        artifact=identity('concern-evidence',concern);fid=identity('concern-finding',concern)
        category={'vocabulary':'unsupported','coverage':'omission','name':'identity','fidelity':'qualification','honorific':'qualification'}.get(concern['category'],concern['category'])
        if category not in {'identity','source','omission','addition','polarity','role','attribution','transmission','qualification','unsupported'}:category='source'
        value['artifacts'].append({'id':artifact,'kind':'review_decision','sha256':digest(concern),'status':'proposed'})
        value['findings'].append({'id':fid,'category':category,'severity':'informational' if concern['status']=='resolved' else 'material',
            'disposition':'resolved' if concern['status']=='resolved' else 'unresolved','targets':[{'kind':'sourceRecords','id':rid} for rid in sorted({owners[s] for s in concern['sourceSpanIds']})],
            'evidenceArtifactIds':[artifact]})
    nonclaim={r['sourceSpanId']:r['status'] for r in output['nonclaimReviews']}
    assessments={rid:identity('stage-assessment',[stamp,rid]) for rid in records}
    for row in output['spanDispositions']:
        rid=owners[row['sourceSpanId']]
        projected={k:copy.deepcopy(row[k]) for k in ('sourceSpanId','status','reasonCode','reportIds','claimIds','ambiguityGroupIds')}
        if row['status']=='nonclaim_form' and nonclaim[row['sourceSpanId']]!='confirmed':projected.update(status='unprocessed',reasonCode='pending')
        projected.update(id=identity('span-disposition',[stamp,row['sourceSpanId']]),sourceRecordVersionId=rid,assessmentIds=[assessments[rid]])
        value['spanDispositions'].append(projected)
    value['currentSourceSelection']=[{'logicalRecordId':r['logicalRecordId'],'sourceRecordVersionId':r['id']} for r in source_records]
    value['currentSpanDispositionSelection']=[{'sourceRecordVersionId':r['sourceRecordVersionId'],'sourceSpanId':r['sourceSpanId'],'spanDispositionId':r['id']} for r in value['spanDispositions']]
    maps={key:graph.indexed(value[key]) for key in graph.COLLECTIONS}
    reviews={r['sourceRecordVersionId']:r for r in output['recordReviews']}
    for rid in records:
        rows=[r for r in value['spanDispositions'] if r['sourceRecordVersionId']==rid]
        targets=[{'kind':'sourceRecords','id':rid},*[{'kind':'spanDispositions','id':r['id']} for r in rows]]
        status=completion_evidence(output,packet,rid,rows,classifications)['status']
        # Confirmed nonclaim rows need their exact positive review evidence even when other record axes remain partial.
        value['assessments'].append({'id':assessments[rid],'kind':['extraction','independent_review','adjudication'][index],
            'targets':targets,'inputs':[{'ref':r,'sha256':digest(maps[r['kind']][r['id']])} for r in targets],
            'status':status,'actorId':actor,'methodArtifactId':method,'effectiveAt':unknown(),'observedAt':unknown(),
            'predecessorIds':[],'findingIds':[],'receiptArtifactIds':[]})
        for row in rows:
            if row['status']=='nonclaim_form':
                # Positive confirmation is represented by a separate exporter-derived assessment.
                aid=identity('nonclaim-review',[stamp,row['id']]);row['assessmentIds'].append(aid)
                refs=[{'kind':'sourceRecords','id':rid},{'kind':'spanDispositions','id':row['id']}]
                value['assessments'].append({'id':aid,'kind':['extraction','independent_review','adjudication'][index],'targets':refs,'inputs':[],
                    'status':'complete','actorId':actor,'methodArtifactId':method,'effectiveAt':unknown(),'observedAt':unknown(),
                    'predecessorIds':[],'findingIds':[],'receiptArtifactIds':[]})
    maps={key:graph.indexed(value[key]) for key in graph.COLLECTIONS}
    for assessment in value['assessments']:
        assessment['inputs']=[{'ref':r,'sha256':digest(maps[r['kind']][r['id']])} for r in assessment['targets']]
    return value


def project_history(history,requested,prior_bundle=None):
    packet=validate_history(history);profile=profile_value();inventory,source_records=inventory_value(packet,profile,requested)
    classifications=baseline_classifications(history['baseline'],packet,read(BASELINE_CLASSIFICATIONS),BASELINE_CLASSIFICATIONS_SHA256)
    stages=[stage_snapshot(item,packet,inventory,source_records,profile,n,classifications) for n,item in enumerate(history['stages'])]
    result=copy.deepcopy(stages[-1]);final={(kind,v['id']) for kind in graph.COLLECTIONS for v in result[kind]}
    previous=None
    if prior_bundle is not None:
        previous=project_history(prior_bundle['history'],prior_bundle['requestedSourceRecordVersionIds'],prior_bundle.get('priorBundle'))
        if previous[3]!=prior_bundle:reject('local-prior-projection-binding-mismatch')
        if previous[1]!=inventory or previous[2]!=profile:reject('local-cumulative-projection-context-mismatch')
        for kind in graph.COLLECTIONS:merge_objects(result[kind],previous[0][kind])
    for stage in stages[:-1]:
        for kind in graph.COLLECTIONS:merge_objects(result[kind],stage[kind])
    decision_artifact=identity('adjudication-proposal',history['stages'][-1]['proposal'])
    result['artifacts'].append({'id':decision_artifact,'kind':'review_decision','sha256':digest(history['stages'][-1]['proposal']),'status':'proposed'})
    # Membership in the final adjudicated proposal selects current objects. Earlier
    # versions remain exact, with explicit exporter-derived retirement metadata.
    already_retired={(r['kind'],r['id']) for event in result['lifecycleEvents'] for r in event['targets']}
    for kind in (*old.COLLECTIONS,'spanDispositions'):
        for value in result[kind]:
            if (kind,value['id']) not in final and (kind,value['id']) not in already_retired:
                result['lifecycleEvents'].append({'id':identity('stage-retirement',[kind,value['id'],decision_artifact]),'kind':'withdraws',
                    'targets':[{'kind':kind,'id':value['id']}],'replacements':[],'decisionArtifactId':decision_artifact,
                    'effectiveAt':unknown(),'dependencyIds':[]})
    receipt_ids=[identity('exporter-derived-receipt',[PROJECTION_VERSION,digest(x['receipt']),digest(inventory),digest(profile),requested]) for x in history['stages']]
    dependencies=sorted(r['id'] for r in source_records if r['id'] not in requested)
    bundle={'schema':'al-isabah.knowledge-local-receipt-bundle.v1','projectionVersion':PROJECTION_VERSION,'derivedBy':'exporter',
            'history':copy.deepcopy(history),'requestedSourceRecordVersionIds':requested,'dependencySourceRecordVersionIds':dependencies,
            'receipts':copy.deepcopy(prior_bundle['receipts']) if prior_bundle else [],
            'bindings':copy.deepcopy(prior_bundle['bindings']) if prior_bundle else [],
            'completionDerivation':[completion_evidence(history['stages'][-1]['proposal']['output'],packet,r['id'],[v for v in stages[-1]['spanDispositions'] if v['sourceRecordVersionId']==r['id']],classifications) for r in source_records]}
    if prior_bundle is not None:bundle['priorBundle']=copy.deepcopy(prior_bundle)
    derived_chain=[]
    for n,(item,stage) in enumerate(zip(history['stages'],stages)):
        outputs=graph.semantic_projection(stage,requested,dependencies)
        inputs={'inventorySha256':digest(inventory),'profileSha256':digest(profile),'sourceRecords':[{'id':r['id'],'sha256':digest(r)} for r in sorted(source_records,key=lambda x:x['id'])],
                'requestedSourceRecordVersionIds':requested,'dependencySourceRecordVersionIds':dependencies,
                'upstreamOutputSha256':derived_chain[-1]['outputSha256'] if n else ''}
        receipt={'schema':PROJECTION_VERSION,'id':receipt_ids[n],'derivedBy':'exporter','stage':old.STAGES[n],
                 'projectionCodeSha256':projection_code_digest(),'sourceReceiptSha256':digest(item['receipt']),'sourceProposalSha256':digest(item['proposal']),
                 'sourceDecisionSha256':digest(history['decision']),'sourceRecordVersionIds':sorted(r['id'] for r in source_records),
                 'inputSha256':digest(inputs),'outputSha256':digest(outputs),'upstreamReceiptIds':receipt_ids[n-1:n]}
        derived_chain.append(receipt);merge_objects(bundle['receipts'],[receipt])
        binding={'receiptId':receipt_ids[n],'inputs':inputs,'outputs':outputs}
        prior_binding=next((b for b in bundle['bindings'] if b['receiptId']==receipt_ids[n]),None)
        if prior_binding is not None and prior_binding!=binding:reject('immutable-id-conflict')
        if prior_binding is None:bundle['bindings'].append(binding)
        result['artifacts'].append({'id':receipt_ids[n],'kind':'knowledge_receipt','sha256':digest(receipt),'status':'proposed'})
    method=identity('method',[PROJECTION_VERSION,projection_code_digest()]);actor=identity('exporter-actor',PROJECTION_VERSION);not_performed=identity('not-performed-actor',PROJECTION_VERSION)
    maps={key:graph.indexed(result[key]) for key in graph.COLLECTIONS};result['assessmentSelection']=[]
    for record in source_records:
        rid=record['id'];rows=[r for r in stages[-1]['spanDispositions'] if r['sourceRecordVersionId']==rid]
        targets=[{'kind':'sourceRecords','id':rid},*[{'kind':'spanDispositions','id':r['id']} for r in rows]]
        status=next(a['status'] for a in stages[-1]['assessments'] if a['kind']=='adjudication' and a['targets']==targets)
        eid=identity('extraction-summary',[digest(history['report']),rid,receipt_ids]);hid=identity('human-unreviewed',[digest(record)])
        for aid,kind,state,who,refs,receipts in [(eid,'extraction',status,actor,targets,receipt_ids),(hid,'human_review','unreviewed',not_performed,[targets[0]],[])]:
            result['assessments'].append({'id':aid,'kind':kind,'status':state,'actorId':who,'methodArtifactId':method,'targets':refs,
                'inputs':[{'ref':r,'sha256':digest(maps[r['kind']][r['id']])} for r in refs],
                'effectiveAt':unknown(kind!='human_review'),'observedAt':unknown(kind!='human_review'),
                'predecessorIds':[],'findingIds':[],'receiptArtifactIds':receipts})
        result['assessmentSelection'].append({'sourceRecordVersionId':rid,'extractionAssessmentId':eid,'humanReviewAssessmentId':hid})
    stamp=digest({'reportSha256':digest(history['report']),'priorBundleSha256':digest(prior_bundle) if prior_bundle else ''});result.update(schemaId='al-isabah.knowledge-snapshot.v2-local1',id=identity('snapshot',[stamp,requested]),
        schemaVersion=VERSION,mode='real',fixtureClass='not-a-fixture',admissionClass='local_provisional',authority=copy.deepcopy(profile['authority']),
        inventorySha256=digest(inventory),profileSha256=digest(profile),receiptBundleSha256=digest(bundle),
        batch={'id':identity('batch',[stamp,requested]),'exportId':identity('export',[stamp,requested]),'selectionMode':'full_snapshot',
               'requestedLogicalRecordIds':sorted(r['id'] for r in inventory['logicalRecords'] if r['inScope']),
               'dependencyLogicalRecordIds':sorted(r['id'] for r in inventory['logicalRecords'] if not r['inScope'])})
    for key in graph.COLLECTIONS:
        unique=[];merge_objects(unique,result[key]);result[key]=sorted(unique,key=lambda x:x['id'])
    for key in ('currentSourceSelection','currentSpanDispositionSelection','assessmentSelection'):result[key].sort(key=graph.canonical)
    return result,inventory,profile,bundle


def validate_projection(snapshot,inventory,profile,bundle):
    expected=project_history(bundle['history'],bundle['requestedSourceRecordVersionIds'],bundle.get('priorBundle'))
    if (snapshot,inventory,profile,bundle)!=expected:reject('local-projection-binding-mismatch')
    return {r['id']:r for r in bundle['receipts']}
