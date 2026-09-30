"""Deterministic synthetic draft2 checkpoints, including immutable corrections."""
import copy
import json
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import knowledge_export_v2_draft3 as k
import knowledge_runtime_draft as runtime
import host_runtime
from knowledge_profile_v3 import proposal
from knowledge_export_v2_support import fixture as draft1_fixture,uid,date


def launch(kind,identity):
    # Exercise actual metadata parsing using authored SYNTHETIC host logs only.
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'synthetic.jsonl'
        path.write_text('\n'.join(json.dumps(x) for x in [
            {'type':'session_meta','payload':{'id':identity,'model_provider':'openai'}},
            {'type':'turn_context','payload':{'turn_id':'turn','model':'gpt-5.6-sol','effort':'xhigh'}}
        ])+'\n',encoding='utf-8')
        observed=host_runtime.observe_session(path,identity,'turn')
    return {'request':host_runtime.launch_request(kind,'gpt-5.6-sol','xhigh'),'observed':observed}


def seal(s,i,p,b):
    for collection in k.COLLECTIONS:s[collection].sort(key=lambda x:x['id'])
    for key in ('currentSourceSelection','assessmentSelection','currentSpanDispositionSelection'):
        s[key].sort(key=lambda x:k.canonical(x))
    s['inventorySha256']=k.digest(i);s['profileSha256']=k.digest(p);s['receiptBundleSha256']=k.digest(b)
    return {'schemaId':'al-isabah.knowledge-draft3-trust.v2','fixtureClass':'synthetic-conformance','snapshotSha256':k.digest(s),'inventorySha256':k.digest(i),'profileSha256':k.digest(p),'schemaSha256':k.digest(k.read(k.SCHEMA_PATH)),'receiptBundleSha256':k.digest(b)}


def bind_assessments(s):
    maps={key:k.indexed(s[key]) for key in k.COLLECTIONS}
    for assessment in s['assessments']:
        assessment['inputs']=[{'ref':copy.deepcopy(r),'sha256':k.digest(maps[r['kind']][r['id']])} for r in assessment['targets']]


def attach_chain(s,i,p,b,registry,label,requested=None,dependencies=()):
    if requested is None:
        current={x['logicalRecordId']:x['sourceRecordVersionId'] for x in s['currentSourceSelection']}
        attach_chain(s,i,p,b,registry,label+'-a',[current[uid('logical',1)],current[uid('logical',3)]])
        attach_chain(s,i,p,b,registry,label+'-b',[current[uid('logical',2)]])
        return
    task=launch('codex-task','synthetic-task-'+label)
    requested=sorted(requested);dependencies=sorted(dependencies)
    record_ids=sorted(requested+dependencies)
    records=k.indexed(s['sourceRecords']);outputs=k.semantic_projection(s,requested,dependencies)
    chain=[]
    for n,stage in enumerate(runtime.STAGES):
        inputs={'inventorySha256':k.digest(i),'profileSha256':k.digest(p),'sourceRecords':[{'id':rid,'sha256':k.digest(records[rid])} for rid in record_ids],'requestedSourceRecordVersionIds':requested,'dependencySourceRecordVersionIds':dependencies,'upstreamOutputSha256':chain[-1]['outputSha256'] if chain else ''}
        receipt=runtime.make_receipt(uid('receipt',label+'-'+str(n)),stage,record_ids,inputs,outputs,task,launch('codex-worker','synthetic-worker-'+label+'-'+str(n)),chain[-1:],registry,'synthetic-conformance')
        b['receipts'].append(receipt);b['bindings'].append({'receiptId':receipt['id'],'inputs':inputs,'outputs':copy.deepcopy(outputs)})
        s['artifacts'].append({'id':receipt['id'],'kind':'knowledge_receipt','sha256':k.digest(receipt),'status':'synthetic_only'})
        chain.append(receipt)
    assessments=k.indexed(s['assessments'])
    for selection in s['assessmentSelection']:
        if selection['sourceRecordVersionId'] not in requested:continue
        assessments[selection['extractionAssessmentId']]['receiptArtifactIds']=[r['id'] for r in chain]


def fixture():
    s,i,p,_=draft1_fixture();registry=k.read(runtime.REGISTRY_PATH)
    s['schemaVersion']='2.0.0-draft.3';i['schemaId']='al-isabah.knowledge-inventory.v2-draft3'
    p.update(schemaId='al-isabah.knowledge-profile.v2-draft3',version='2.0.0-draft.3',methodRegistrySha256=k.digest(registry))
    s['currentSourceSelection']=[{'logicalRecordId':r['logicalRecordId'],'sourceRecordVersionId':r['id']} for r in s['sourceRecords']]
    s['names']=[];s['currentSpanDispositionSelection']=[]
    for entity in s['entities']:
        entity['logicalEntityId']=entity['id'].replace(':entities:',':logical-entity:');entity['nameIds']=[]
    for n,mention in enumerate(s['mentions'],1):
        identity=uid('names',n);mention['nameId']=identity
        name={'id':identity,'entityId':mention['entityId'],'language':'en','form':'Synthetic Alpha' if n==1 else 'Synthetic Beta','formRole':mention['nameRole'],'derivation':'transliteration','sourceRecordVersionId':mention['sourceRecordVersionId'],'sourceSpanId':mention['sourceSpanId'],'sourceSurfaceSha256':mention['surfaceSha256'],'assessmentIds':[],'ambiguityGroupIds':[]}
        s['names'].append(name);next(e for e in s['entities'] if e['id']==name['entityId'])['nameIds'].append(identity)
    for value in s['values']:value['amountNumerator']=value.pop('amount');value['amountDenominator']=1
    for assessment in s['assessments']:assessment['receiptArtifactIds']=[]
    for row in s['spanDispositions']:
        span=next(x for x in i['sourceSpans'] if x['id']==row['sourceSpanId'])
        record=next(x for x in s['sourceRecords'] if span['sourceUnitId'] in x['authorityUnitIds'])
        row['sourceRecordVersionId']=record['id']
        s['currentSpanDispositionSelection'].append({'sourceRecordVersionId':record['id'],'sourceSpanId':span['id'],'spanDispositionId':row['id']})
        selection=next(x for x in s['assessmentSelection'] if x['sourceRecordVersionId']==record['id'])
        extraction=next(x for x in s['assessments'] if x['id']==selection['extractionAssessmentId'])
        extraction['targets'].append({'kind':'spanDispositions','id':row['id']})
    p=proposal(p,synthetic=True)
    for claim in s['claims']:claim['subjectRef']={'kind':'entities','id':claim.pop('subjectId')}
    bind_assessments(s)
    b={'schema':'al-isabah.knowledge-receipt-bundle.v1-draft','fixtureClass':'synthetic-conformance','registrySha256':k.digest(registry),'receipts':[],'bindings':[]}
    attach_chain(s,i,p,b,registry,'initial')
    return s,i,p,seal(s,i,p,b),b,registry


def new_snapshot_ids(s,label):
    s['id']=uid('snapshot',label);s['batch']['id']=uid('batch',label);s['batch']['exportId']=uid('export',label)


def correction(base,source_change):
    s,i,p,_,b,registry=copy.deepcopy(base);label='source-correction' if source_change else 'extraction-correction'
    new_snapshot_ids(s,label)
    original={key:copy.deepcopy(s[key]) for key in k.COLLECTIONS}
    replacements={}
    kinds=[c for c in k.COLLECTIONS if c not in {'sourceRecords','actors','artifacts','lifecycleEvents'}]
    for kind in kinds:
        replacements.update({v['id']:v['id']+'-'+label for v in original[kind]})
    if source_change:replacements[uid('sourceRecords',1)]=uid('sourceRecords',1)+'-'+label
    def replace(value):
        if isinstance(value,str):return replacements.get(value,value)
        if isinstance(value,list):return [replace(x) for x in value]
        if isinstance(value,dict):return {key:replace(child) for key,child in value.items()}
        return value
    for kind in kinds+(['sourceRecords'] if source_change else []):
        for old in original[kind]:
            if old['id'] not in replacements:continue
            new=replace(old)
            if kind=='sourceRecords':new['recordSha256']=k.digest('synthetic-corrected-record-bytes')
            if kind=='assessments':new['receiptArtifactIds']=[]
            s[kind].append(new)
            s['lifecycleEvents'].append({'id':uid('lifecycleEvents',label+'-'+kind.lower()+'-'+old['id'].rsplit(':',1)[-1]),'kind':'corrects','targets':[{'kind':kind,'id':old['id']}],'replacements':[{'kind':kind,'id':new['id']}],'effectiveAt':date(True),'decisionArtifactId':uid('artifacts',4),'dependencyIds':[]})
    for key in ('currentSourceSelection','assessmentSelection','currentSpanDispositionSelection'):s[key]=replace(s[key])
    # Only successor assessments may change; history remains byte-identical.
    maps={key:k.indexed(s[key]) for key in k.COLLECTIONS}
    for assessment in s['assessments']:
        if assessment['id'] in replacements.values():
            assessment['inputs']=[{'ref':copy.deepcopy(r),'sha256':k.digest(maps[r['kind']][r['id']])} for r in assessment['targets']]
    attach_chain(s,i,p,b,registry,label)
    return s,i,p,seal(s,i,p,b),b,registry


def reaffirmation(base):
    s,i,p,_,b,registry=copy.deepcopy(base);label='reaffirmation';new_snapshot_ids(s,label)
    amap=k.indexed(s['assessments'])
    for selection in s['assessmentSelection']:
        old=amap[selection['extractionAssessmentId']];new=copy.deepcopy(old)
        new['id']=old['id']+'-'+label;new['predecessorIds']=[old['id']];new['receiptArtifactIds']=[]
        s['assessments'].append(new);selection['extractionAssessmentId']=new['id']
        s['lifecycleEvents'].append({'id':uid('lifecycleEvents',label+'-'+old['id'].rsplit(':',1)[-1]),'kind':'supersedes','targets':[{'kind':'assessments','id':old['id']}],'replacements':[{'kind':'assessments','id':new['id']}],'effectiveAt':date(True),'decisionArtifactId':uid('artifacts',4),'dependencyIds':[]})
    attach_chain(s,i,p,b,registry,label)
    return s,i,p,seal(s,i,p,b),b,registry


def independent_correction(base):
    s,i,p,_,b,registry=copy.deepcopy(base);label='independent-correction';new_snapshot_ids(s,label)
    rid=uid('sourceRecords',2)
    selection=next(x for x in s['assessmentSelection'] if x['sourceRecordVersionId']==rid)
    row_selection=next(x for x in s['currentSpanDispositionSelection'] if x['sourceRecordVersionId']==rid)
    old_a=next(x for x in s['assessments'] if x['id']==selection['extractionAssessmentId'])
    old_row=next(x for x in s['spanDispositions'] if x['id']==row_selection['spanDispositionId'])
    new_a=copy.deepcopy(old_a);new_a['id']+='-'+label;new_a['receiptArtifactIds']=[]
    new_row=copy.deepcopy(old_row);new_row['id']+='-'+label;new_row['assessmentIds']=[new_a['id']]
    new_a['targets']=[{'kind':'sourceRecords','id':rid},{'kind':'spanDispositions','id':new_row['id']}]
    record=next(x for x in s['sourceRecords'] if x['id']==rid)
    new_a['inputs']=[{'ref':new_a['targets'][0],'sha256':k.digest(record)},{'ref':new_a['targets'][1],'sha256':k.digest(new_row)}]
    s['assessments'].append(new_a);s['spanDispositions'].append(new_row)
    selection['extractionAssessmentId']=new_a['id'];row_selection['spanDispositionId']=new_row['id']
    for kind,old,new in [('assessments',old_a,new_a),('spanDispositions',old_row,new_row)]:
        s['lifecycleEvents'].append({'id':uid('lifecycleEvents',label+'-'+kind.lower()),'kind':'corrects','targets':[{'kind':kind,'id':old['id']}],'replacements':[{'kind':kind,'id':new['id']}],'effectiveAt':date(True),'decisionArtifactId':uid('artifacts',4),'dependencyIds':[]})
    attach_chain(s,i,p,b,registry,label,[rid])
    return s,i,p,seal(s,i,p,b),b,registry


def refresh(data,label='fresh'):
    s,i,p,_,b,registry=copy.deepcopy(data)
    s['artifacts']=[a for a in s['artifacts'] if a['kind']!='knowledge_receipt']
    b['receipts']=[];b['bindings']=[]
    for a in s['assessments']:a['receiptArtifactIds']=[]
    bind_assessments(s);attach_chain(s,i,p,b,registry,label)
    return s,i,p,seal(s,i,p,b),b,registry


def capabilities():
    data=copy.deepcopy(fixture());s,i,p,_,b,registry=data
    r1=uid('sourceRecords',1);r3=uid('sourceRecords',3);span=uid('span',1);author=uid('entities',1)
    report=next(r for r in s['reports'] if r['id']==uid('reports',1))
    report['attributorEntityIds']=[author]
    row=next(x for x in s['spanDispositions'] if x['sourceSpanId']==span)
    event_names=['pregnancy','birth','purification','oath','grant','supplication','journey']
    for name in event_names:
        s['events'].append({'id':uid('events',name),'typeId':uid('event-type',name),'participantRoles':[{'roleId':p['participantRoles'][0],'entityId':author}],'placeIds':[],'timeIds':[],'sourceRecordVersionIds':[r1],'reportIds':[report['id']],'ambiguityGroupIds':[]})
    s['values'].append({'id':uid('values','pledge'),'amountNumerator':7,'amountDenominator':2,'approximate':True,'kind':'count','unit':'camels','sourceRecordVersionIds':[r1]})
    s['useRestrictions'].append({'id':uid('useRestrictions','qualified'),'tier':'qualified_context','attributionRequired':True})
    def claim(name,subject,kind,target,polarity='positive',modality='asserted',records=None):
        cid=uid('claims',name);qid=uid('qualifications',name)
        s['claims'].append({'id':cid,'subjectRef':subject,'predicateId':uid('predicate',name),'objectRef':{'kind':kind,'id':target},'sourceRecordVersionIds':records or [r1],'sourceSpanIds':[span],'reportIds':[report['id']],'assertionClass':'source_attested','polarity':polarity,'modality':modality,'qualificationIds':[qid],'assessmentIds':[],'attributionIds':[uid('attributions',1)],'ambiguityGroupIds':[],'useRestrictionIds':[uid('useRestrictions','qualified')]})
        s['qualifications'].append({'id':qid,'targets':[{'kind':'claims','id':cid}],'evaluatorEntityIds':[author],'criticalStatus':'qualified','evidentiaryStrength':'source_supported','transmissionStrength':'unassessed','sourceRecordVersionIds':records or [r1]})
        report['claimIds'].append(cid);row['claimIds'].append(cid)
    person={'kind':'entities','id':author}
    for name in ('nursing-sibling-of','foster-parent-of'):claim(name,person,'entities',uid('entities',2))
    for name in ('companion-status-inferred-from','companion-status-evidence-in','emigrant-status-attested-in'):
        claim(name,person,'sourceRecords',r3,polarity='absence_of_evidence' if name=='companion-status-evidence-in' else 'positive',records=[r1,r3])
    ev=lambda name:{'kind':'events','id':uid('events',name)}
    claim('precedes',ev('pregnancy'),'events',uid('events','birth'))
    claim('conditioned-on',ev('purification'),'events',uid('events','birth'),modality='conditional')
    claim('requests-outcome',ev('supplication'),'events',uid('events','birth'))
    claim('pledged-quantity',ev('oath'),'values',uid('values','pledge'))
    claim('granted-place',ev('grant'),'places',uid('places',1))
    for name in ('departed-from','arrived-at'):claim(name,ev('journey'),'places',uid('places',1))
    route={'id':uid('reports','additional-route'),'sourceRecordVersionIds':[r1],'sourceSpanIds':[span],'attributorEntityIds':[author],'transmission':[{'position':0,'role':'transmitter','entityIds':[uid('entities',2)],'ambiguityGroupIds':[]}],'claimIds':[],'criticalAssessmentIds':[],'ambiguityGroupIds':[]}
    s['reports'].append(route);row['reportIds'].append(route['id'])
    return refresh(data,'capabilities')


def helper_input(snapshot):
    import knowledge_successors as helper
    objects=[{'kind':kind,'value':copy.deepcopy(value)} for kind in helper.MUTABLE for value in snapshot[kind]]
    present={(x['kind'],x['value']['id']) for x in objects}
    refs=set().union(*(helper.references(x['value']) for x in objects))-present
    return {'schema':'al-isabah.knowledge-edit-input.v1','objects':objects,'externalRefs':[{'kind':kind,'id':identity} for kind,identity in sorted(refs)]}


def helper_correction(base):
    import knowledge_successors as helper
    s,i,p,_,b,registry=copy.deepcopy(base);label='helper-correction';new_snapshot_ids(s,label)
    source=helper_input(base[0]);old=next(x for x in source['objects'] if x['kind']=='qualifications' and x['value']['id']==uid('qualifications','pledged-quantity'))['value']
    changed=copy.deepcopy(old);changed['criticalStatus']='disputed'
    patches=[{'ref':{'kind':'qualifications','id':old['id']},'beforeSha256':k.digest(old),'replacement':changed}]
    plan=helper.plan(source,k.digest(source),patches,uid('successor','reviewed'))
    mapping={(r['from']['kind'],r['from']['id']):r['to']['id'] for r in plan['replacements']}
    for n,row in enumerate(plan['replacements']):
        s[row['from']['kind']].append(copy.deepcopy(row['value']))
        s['lifecycleEvents'].append({'id':uid('lifecycleEvents',label+'-'+str(n)),'kind':'corrects','targets':[row['from']],'replacements':[row['to']],'effectiveAt':date(True),'decisionArtifactId':uid('artifacts',4),'dependencyIds':[]})
    affected=set()
    rows=k.indexed(s['spanDispositions'])
    for selection in s['currentSpanDispositionSelection']:
        old=rows[selection['spanDispositionId']];new=helper.rewire(old,mapping)
        if new==old:continue
        new['id']=old['id']+'-'+label
        s['spanDispositions'].append(new);selection['spanDispositionId']=new['id'];affected.add(selection['sourceRecordVersionId'])
        s['lifecycleEvents'].append({'id':uid('lifecycleEvents',label+'-row-'+str(len(affected))+'-'+str(len(s['spanDispositions']))),'kind':'corrects','targets':[{'kind':'spanDispositions','id':old['id']}],'replacements':[{'kind':'spanDispositions','id':new['id']}],'effectiveAt':date(True),'decisionArtifactId':uid('artifacts',4),'dependencyIds':[]})
    amap=k.indexed(s['assessments'])
    for selection in s['assessmentSelection']:
        rid=selection['sourceRecordVersionId']
        if rid not in affected:continue
        old=amap[selection['extractionAssessmentId']];new=copy.deepcopy(old);new['id']+='-'+label;new['predecessorIds']=[];new['receiptArtifactIds']=[]
        new['targets']=[{'kind':'sourceRecords','id':rid}]+[{'kind':'spanDispositions','id':r['spanDispositionId']} for r in s['currentSpanDispositionSelection'] if r['sourceRecordVersionId']==rid]
        s['assessments'].append(new);selection['extractionAssessmentId']=new['id']
        s['lifecycleEvents'].append({'id':uid('lifecycleEvents',label+'-assessment-'+rid.rsplit(':',1)[-1]),'kind':'supersedes','targets':[{'kind':'assessments','id':old['id']}],'replacements':[{'kind':'assessments','id':new['id']}],'effectiveAt':date(True),'decisionArtifactId':uid('artifacts',4),'dependencyIds':[]})
        for row in s['spanDispositions']:
            if row['sourceRecordVersionId']==rid and row['id'].endswith('-'+label):row['assessmentIds']=[new['id']]
    # Only new assessments get new input bindings; historical bytes stay exact.
    maps={kind:k.indexed(s[kind]) for kind in k.COLLECTIONS}
    for a in s['assessments']:
        if a['id'].endswith('-'+label):a['inputs']=[{'ref':copy.deepcopy(ref),'sha256':k.digest(maps[ref['kind']][ref['id']])} for ref in a['targets']]
    attach_chain(s,i,p,b,registry,label,sorted(affected))
    return s,i,p,seal(s,i,p,b),b,registry


def repin_adversarial(data):
    """Authored SYNTHETIC tampering: repair hashes without repairing semantics."""
    s,i,p,_,b,registry=copy.deepcopy(data)
    bind_assessments(s)
    maps={kind:{x['id']:x for x in s[kind]} for kind in k.COLLECTIONS}
    receipts={r['id']:r for r in b['receipts']}
    for binding in b['bindings']:
        receipt=receipts[binding['receiptId']]
        inputs=binding['inputs'];inputs['profileSha256']=k.digest(p);inputs['inventorySha256']=k.digest(i)
        for row in inputs['sourceRecords']:
            if row['id'] in maps['sourceRecords']:row['sha256']=k.digest(maps['sourceRecords'][row['id']])
        if receipt['upstreamReceiptIds']:inputs['upstreamOutputSha256']=receipts[receipt['upstreamReceiptIds'][0]]['outputSha256']
        for row in binding['outputs']['objects']:
            ref=row['ref']
            if ref['id'] in maps[ref['kind']]:row['sha256']=k.digest(maps[ref['kind']][ref['id']])
        receipt['inputSha256']=k.digest(inputs);receipt['outputSha256']=k.digest(binding['outputs'])
        receipt['checkpointSha256']=runtime.checkpoint(receipt);receipt['receiptSha256']=k.digest({a:v for a,v in receipt.items() if a!='receiptSha256'})
        maps['artifacts'][receipt['id']]['sha256']=k.digest(receipt)
    return s,i,p,seal(s,i,p,b),b,registry


def apply_case(base,case):
    data=list(copy.deepcopy(base));inputs={'snapshot':data[0],'inventory':data[1],'profile':data[2]}
    for patch in case['patches']:
        target=inputs[patch['input']]
        for part in patch['path'][:-1]:target=target[part]
        key=patch['path'][-1]
        if patch['op']=='append':target[key].append(copy.deepcopy(patch['value']))
        elif patch['op']=='remove':del target[key]
        else:target[key]=copy.deepcopy(patch['value'])
    if case['repin']=='all_synthetic_bindings':return repin_adversarial(data)
    data[3]=seal(data[0],data[1],data[2],data[4])
    return data


def adversarial_cases():
    old=k.read(ROOT/'tests/fixtures/knowledge-export-v2-draft2/adversarial-cases.json')
    cases=[{**copy.deepcopy(c),'fixture':'initial','repin':'external_pins'} for c in old['cases']]
    base=capabilities();s=base[0]
    idx=lambda kind,name:next(n for n,x in enumerate(s[kind]) if x['id']==uid(kind,name))
    def change(path,value,op='set',input='snapshot'):return {'input':input,'op':op,'path':path,'value':value}
    def add(name,code,*patches):cases.append({'id':name,'fixture':'capabilities','repin':'all_synthetic_bindings','expectedCode':code,'patches':list(patches)})
    c=idx('claims','companion-status-evidence-in');q=idx('qualifications','companion-status-evidence-in')
    factual={'id':uid('useRestrictions','forbidden-factual'),'tier':'factual_spine','attributionRequired':True}
    for polarity in ('negative','positive','absence_of_evidence'):
        add('notice-joint-upgrade-'+polarity,'predicate-epistemic-mismatch',change(['claims',c,'polarity'],polarity),change(['qualifications',q,'criticalStatus'],'unqualified'),change(['qualifications',q,'evidentiaryStrength'],'source_supported'),change(['useRestrictions'],factual,'append'),change(['claims',c,'useRestrictionIds'],[factual['id']]))
    add('mixed-allowed-forbidden-tiers','predicate-epistemic-mismatch',change(['useRestrictions'],factual,'append'),change(['claims',c,'useRestrictionIds'],[uid('useRestrictions','qualified'),factual['id']]))
    add('source-inference-is-not-agent-inference','predicate-epistemic-mismatch',change(['claims',idx('claims','companion-status-inferred-from'),'assertionClass'],'inferred'))
    for name in ('conditioned-on','requests-outcome','pledged-quantity'):
        add(name+'-factual-fulfillment','predicate-epistemic-mismatch',change(['useRestrictions'],factual,'append'),change(['claims',idx('claims',name),'useRestrictionIds'],[factual['id']]))
    add('condition-loses-conditional-modality','predicate-epistemic-mismatch',change(['claims',idx('claims','conditioned-on'),'modality'],'asserted'))
    add('legacy-subject-field','prohibited-payload',change(['claims',c,'subjectId'],uid('entities',1)))
    add('unknown-subject-kind','schema-mismatch',change(['claims',c,'subjectRef','kind'],'reports'))
    add('entity-predicate-event-subject','reference-kind-mismatch',change(['claims',c,'subjectRef'],{'kind':'events','id':uid('events','birth')}))
    add('wrong-subject-event-type','predicate-domain-mismatch',change(['claims',idx('claims','pledged-quantity'),'subjectRef','id'],uid('events','birth')))
    add('wrong-target-event-type','predicate-domain-mismatch',change(['events',idx('events','birth'),'typeId'],uid('event-type','unapproved')))
    add('event-reference-missing','missing-reference',change(['claims',idx('claims','precedes'),'subjectRef','id'],uid('events','absent')))
    add('event-evidence-foreign-owner','event-evidence-mismatch',change(['events',idx('events','oath'),'sourceRecordVersionIds'],[uid('sourceRecords',3)]))
    add('event-evidence-missing','event-evidence-missing',change(['events',idx('events','oath'),'reportIds'],[]))
    add('place-wrapper-points-to-person','place-domain-mismatch',change(['places',0,'entityId'],uid('entities',1)))
    add('pledge-person-unit','value-domain-mismatch',change(['values',idx('values','pledge'),'unit'],'persons'))
    add('camel-duration','value-domain-mismatch',change(['values',idx('values','pledge'),'kind'],'duration'))
    add('unknown-unit-same-profile','value-domain-mismatch',change(['values',idx('values','pledge'),'unit'],'unknown_unit'))
    add('fraction-zero-denominator','schema-mismatch',change(['values',idx('values','pledge'),'amountDenominator'],0))
    add('work-is-not-source-author','source-author-attribution-mismatch',change(['attributions',0,'kind'],'work'))
    add('license-is-not-source-author','source-author-attribution-mismatch',change(['attributions',0,'kind'],'license'))
    add('unrelated-author-artifact','source-author-attribution-mismatch',change(['attributions',0,'artifactIds'],[uid('artifacts',4)]))
    add('machine-actor-is-not-author-entity','missing-reference',change(['attributions',0,'entityIds'],[s['actors'][0]['id']]))
    add('notice-logical-id-not-version','missing-reference',change(['claims',c,'objectRef','id'],uid('logical',3)))
    add('notice-missing-version','missing-reference',change(['claims',c,'objectRef','id'],uid('sourceRecords','absent')))
    add('notice-not-in-declared-sources','notice-evidence-mismatch',change(['claims',c,'objectRef','id'],uid('sourceRecords',2)))
    add('attesting-span-wrong-owner','source-identity-mismatch',change(['claims',c,'sourceSpanIds'],[uid('span',3)]))
    # Author on a distractor report or qualification cannot serve the attesting span.
    add('distractor-report-author','source-author-attribution-mismatch',change(['reports',idx('reports',1),'attributorEntityIds'],[uid('entities',2)]),change(['claims',c,'reportIds'],[uid('reports',1),uid('reports',2)]),change(['reports',idx('reports',2),'attributorEntityIds'],[uid('entities',1)]),change(['reports',idx('reports',2),'claimIds'],uid('claims','companion-status-evidence-in'),'append'))
    add('distractor-evaluator','source-author-attribution-mismatch',change(['qualifications',q,'evaluatorEntityIds'],[uid('entities',2)]),change(['qualifications',q,'sourceRecordVersionIds'],[uid('sourceRecords',1)]),change(['claims',c,'qualificationIds'],[uid('qualifications','companion-status-evidence-in'),uid('qualifications',2)]),change(['qualifications',idx('qualifications',2),'targets'],{'kind':'claims','id':uid('claims','companion-status-evidence-in')},'append'))
    for kind,name in [('events','oath'),('values','pledge'),('places',1),('sourceRecords',3)]:
        event={'id':uid('lifecycleEvents','retired-'+kind.lower()),'kind':'withdraws','targets':[{'kind':kind,'id':uid(kind,name)}],'replacements':[],'effectiveAt':date(True),'decisionArtifactId':uid('artifacts',4),'dependencyIds':[]}
        add('retired-'+kind.lower()+'-dependency','active-reference-retired',change(['lifecycleEvents'],event,'append'))
    return {'schema':'al-isabah.knowledge-export-v2-draft3.adversarial-cases.v1','fixtureClass':'synthetic-conformance','cases':cases}


def export(data):
    s,i,p,t,b,r=data
    return k.build(s,i,p,t,s['batch']['id'],b,r)


if __name__=='__main__':
    directory=ROOT/'tests/fixtures/knowledge-export-v2-draft3';directory.mkdir(parents=True,exist_ok=True)
    base=fixture()
    for label,data in [('initial',base),('capabilities',capabilities()),('helper-correction',helper_correction(capabilities())),('source-correction',correction(base,True)),('extraction-correction',correction(base,False)),('reaffirmation',reaffirmation(base)),('independent-correction',independent_correction(base))]:
        payload=export(data)
        target=directory/label;target.mkdir(exist_ok=True)
        for name,value in zip(('snapshot','inventory','profile','trust','receipts','knowledge-method-registry'),data):(target/(name+'.json')).write_bytes(k.canonical(value))
        (target/'batch.json').write_bytes(k.canonical(payload))
    (directory/'adversarial-cases.json').write_bytes(k.canonical(adversarial_cases()))
    print('synthetic-draft3-fixtures-written')
