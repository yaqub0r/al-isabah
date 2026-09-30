"""Authored synthetic v2 conformance; no real text or historical assertions."""
import copy
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import knowledge_export_v2 as k

def uid(kind,n):return f'urn:al-isabah:synthetic:{kind.lower()}:{n}'
def ref(kind,n):return {'kind':kind,'id':uid(kind,n)}
def date(known=False):return {'status':'recorded' if known else 'unknown','timestamp':'2000-01-01T00:00:00Z' if known else '', 'reasonCode':'none' if known else 'not_performed'}
def seal(s,i,p):
 s['inventorySha256']=k.digest(i);s['profileSha256']=k.digest(p)
 return {'schemaId':'al-isabah.knowledge-draft-trust.v2','fixtureClass':'synthetic-conformance','snapshotSha256':k.digest(s),'inventorySha256':k.digest(i),'profileSha256':k.digest(p),'schemaSha256':k.digest(k.read(k.SCHEMA_PATH))}
def fixture():
 h=k.digest
 authority={'id':uid('authority',1),'workId':uid('work',1),'editionId':uid('edition',1),'revisionId':uid('revision',1),'sourceArtifactSha256':h('synthetic-authority'),'verificationBasis':'synthetic'}
 units=[{'id':uid('unit',n),'kind':'structural_heading' if n==2 else 'entry','ownerEntryId':uid('unit',1 if n==2 else n),'rawSha256':h(['unit',n]),'locations':[{'volume':8 if n<4 else 1,'page':n}],'inScope':n<4} for n in range(1,5)]
 logical=[{'id':uid('logical',n),'sourceUnitIds':[uid('unit',u) for u in ([1,2] if n==1 else [n+1])],'inScope':n<3} for n in range(1,4)]
 inventory={'schemaId':'al-isabah.knowledge-inventory.v2-draft','id':uid('inventory',1),'authority':authority,'selectedScopeSha256':h('synthetic-selected-scope'),'sourceUnits':units,'logicalRecords':logical,'sourceSpans':[{'id':uid('span',n),'sourceUnitId':uid('unit',n),'sha256':h(['span',n])} for n in range(1,5)],'reconciliationStatus':'synthetic','reconciliationEvidenceSha256':h('synthetic-crosswalk')}
 predicates=[{'id':uid('predicate',1),'family':'relationship','subjectKinds':['person'],'objectKinds':['entities'],'objectEntityKinds':['person'],'directional':True},{'id':uid('predicate',2),'family':'event','subjectKinds':['person'],'objectKinds':['events'],'objectEntityKinds':[],'directional':True},{'id':uid('predicate',3),'family':'context','subjectKinds':['person'],'objectKinds':['values'],'objectEntityKinds':[],'directional':True}]
 profile={'schemaId':'al-isabah.knowledge-profile.v2-draft','id':uid('profile',1),'version':'2.0.0-draft.1','status':'draft','mode':'synthetic','realExecutionEnabled':False,'realAdmissionEnabled':False,'authority':authority,'selectedScopeSha256':inventory['selectedScopeSha256'],'predicates':predicates,'eventTypes':[uid('event-type',1)],'participantRoles':[uid('role',1)],'reasonCodes':['mapped','uncertain','heading','formula_only','bibliographic_format','unsupported','pending','source_damage','mapping_unverified'],'rights':{'basis':'synthetic_testing_only','attributionRequired':True,'commercialUse':'not_granted','shareAlike':True,'approvalStatus':'not_approved_for_real_intake'}}
 s={'schemaId':'al-isabah.knowledge-snapshot.v2','id':uid('snapshot',1),'schemaVersion':'2.0.0-draft.1','mode':'synthetic','fixtureClass':'synthetic-conformance','profileSha256':'0'*64,'inventorySha256':'0'*64,'authority':authority,'assessmentSelection':[],'batch':{'id':uid('batch',1),'exportId':uid('export',1),'requestedLogicalRecordIds':[uid('logical',1),uid('logical',2)],'dependencyLogicalRecordIds':[uid('logical',3)],'selectionMode':'full_snapshot'},**{c:[] for c in k.COLLECTIONS}}
 s['artifacts']=[{'id':uid('artifacts',n),'kind':kind,'sha256':h(['artifact',n]),'status':'synthetic_only'} for n,kind in enumerate(['source_derivation','method','actor_authority','review_decision'],1)]
 s['actors']=[{'id':uid('actors',n),'kind':kind,'authorityArtifactId':uid('artifacts',3)} for n,kind in [(1,'machine'),(2,'not_performed')]]
 for n in range(1,4):
  record={'id':uid('sourceRecords',n),'logicalRecordId':uid('logical',n),'authorityUnitIds':logical[n-1]['sourceUnitIds'],'recordSha256':h(['upstream-record-bytes',n]),'sourceArtifactId':uid('artifacts',1)};s['sourceRecords'].append(record)
  for offset,kind,status in [(0,'extraction','partial' if n==2 else 'complete'),(1,'human_review','unreviewed')]:
   aid=uid('assessments',n*2+offset)
   s['assessments'].append({'id':aid,'kind':kind,'targets':[ref('sourceRecords',n)],'inputs':[{'ref':ref('sourceRecords',n),'sha256':h(record)}],'status':status,'actorId':uid('actors',1 if offset==0 else 2),'methodArtifactId':uid('artifacts',2),'effectiveAt':date(offset==0),'observedAt':date(offset==0),'predecessorIds':[],'findingIds':[]})
  s['assessmentSelection'].append({'sourceRecordVersionId':record['id'],'extractionAssessmentId':uid('assessments',n*2),'humanReviewAssessmentId':uid('assessments',n*2+1)})
 s['entities']=[{'id':uid('entities',n),'kind':'place' if n==3 else 'person','sourceRecordVersionIds':[uid('sourceRecords',3 if n==2 else 1)],'mentionIds':[uid('mentions',n)] if n<3 else [],'identityAssessmentIds':[],'ambiguityGroupIds':[]} for n in range(1,4)]
 s['mentions']=[{'id':uid('mentions',n),'entityId':uid('entities',n),'sourceRecordVersionId':uid('sourceRecords',1 if n==1 else 3),'sourceSpanId':uid('span',1 if n==1 else 4),'surfaceSha256':h(['synthetic-name',n]),'nameRole':'alias' if n==2 else 'name','ambiguityGroupIds':[]} for n in (1,2)]
 s['places']=[{'id':uid('places',1),'entityId':uid('entities',3),'certainty':'source_named','ambiguityGroupIds':[],'sourceRecordVersionIds':[uid('sourceRecords',1)]}]
 s['times']=[{'id':uid('times',1),'calendar':'relative','earliest':10,'latest':12,'precision':'day','approximate':True,'ambiguityGroupIds':[],'sourceRecordVersionIds':[uid('sourceRecords',1)]}]
 s['values']=[{'id':uid('values',1),'kind':'count','amount':2,'unit':'persons','approximate':False,'sourceRecordVersionIds':[uid('sourceRecords',1)]}]
 s['events']=[{'id':uid('events',1),'typeId':uid('event-type',1),'participantRoles':[{'roleId':uid('role',1),'entityId':uid('entities',1)}],'placeIds':[uid('places',1)],'timeIds':[uid('times',1)],'sourceRecordVersionIds':[uid('sourceRecords',1)],'reportIds':[uid('reports',1)],'ambiguityGroupIds':[]}]
 for n in range(1,5):
  record=3 if n==2 else 1; span=4 if n==2 else 1; report=2 if n==2 else 1
  s['claims'].append({'id':uid('claims',n),'reportIds':[uid('reports',report)],'sourceRecordVersionIds':[uid('sourceRecords',record)],'sourceSpanIds':[uid('span',span)],'subjectId':uid('entities',1),'predicateId':uid('predicate',1 if n<3 else n-1),'objectRef':ref('entities',2) if n<3 else ref('events' if n==3 else 'values',1),'assertionClass':'source_attested','polarity':'negative' if n==2 else 'positive','modality':'disputed' if n<3 else 'asserted','qualificationIds':[uid('qualifications',n)],'assessmentIds':[],'attributionIds':[uid('attributions',1)],'ambiguityGroupIds':[uid('ambiguityGroups',1)] if n<3 else [],'useRestrictionIds':[uid('useRestrictions',1)]})
  s['qualifications'].append({'id':uid('qualifications',n),'targets':[ref('claims',n)],'evaluatorEntityIds':[uid('entities',1)],'criticalStatus':'disputed' if n<3 else 'qualified','evidentiaryStrength':'unassessed','transmissionStrength':'unassessed','sourceRecordVersionIds':[uid('sourceRecords',record)]})
 s['reports']=[{'id':uid('reports',n),'sourceRecordVersionIds':[uid('sourceRecords',1 if n==1 else 3)],'sourceSpanIds':[uid('span',1 if n==1 else 4)],'attributorEntityIds':[uid('entities',1)],'transmission':[{'position':0,'role':'speaker','entityIds':[uid('entities',1)],'ambiguityGroupIds':[]},{'position':1,'role':'transmitter','entityIds':[uid('entities',2)],'ambiguityGroupIds':[]}],'claimIds':[uid('claims',i) for i in ([1,3,4] if n==1 else [2])],'criticalAssessmentIds':[],'ambiguityGroupIds':[]} for n in (1,2)]
 s['ambiguityGroups']=[{'id':uid('ambiguityGroups',1),'kind':'report_alternatives','members':[ref('claims',1),ref('claims',2)],'sourceRecordVersionIds':[uid('sourceRecords',1),uid('sourceRecords',3)],'assessmentIds':[],'resolutionState':'represented_alternatives'}]
 s['attributions']=[{'id':uid('attributions',1),'kind':'source_author','entityIds':[uid('entities',1)],'artifactIds':[uid('artifacts',1)],'required':True}]
 s['useRestrictions']=[{'id':uid('useRestrictions',1),'tier':'attributed_disputed_report','attributionRequired':True}]
 for n,status,reason in [(1,'represented_uncertain','uncertain'),(2,'structural_only','heading'),(3,'unsupported_semantics','unsupported'),(4,'represented_uncertain','uncertain')]:
  represented=n in (1,4); record=3 if n==4 else 2 if n==3 else 1
  s['spanDispositions'].append({'id':uid('spanDispositions',n),'sourceSpanId':uid('span',n),'status':status,'reasonCode':reason,'reportIds':[uid('reports',1 if n==1 else 2)] if represented else [],'claimIds':[uid('claims',i) for i in ([1,3,4] if n==1 else [2])] if represented else [],'ambiguityGroupIds':[uid('ambiguityGroups',1)] if represented else [],'assessmentIds':[uid('assessments',record*2)]})
 s['findings']=[{'id':uid('findings',1),'targets':[ref('sourceRecords',2)],'category':'unsupported','severity':'blocking','disposition':'unresolved','evidenceArtifactIds':[uid('artifacts',1)]}]
 next(x for x in s['assessments'] if x['id']==uid('assessments',4))['findingIds']=[uid('findings',1)]
 for key in k.COLLECTIONS:s[key].sort(key=lambda x:x['id'])
 return s,inventory,profile,seal(s,inventory,profile)

def export(s,i,p,t):return k.build(s,i,p,t,s['batch']['id'])

if __name__=='__main__':
 s,i,p,t=fixture();directory=ROOT/'tests/fixtures/knowledge-export-v2-draft';directory.mkdir(parents=True,exist_ok=True)
 for name,value in [('snapshot',s),('inventory',i),('profile',p),('trust',t),('batch',export(s,i,p,t))]:(directory/(name+'.json')).write_bytes(k.canonical(value))
 print('synthetic-v2-fixtures-written')
