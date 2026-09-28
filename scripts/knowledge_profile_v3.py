"""Deterministic draft3 profile proposal; no approval or execution enablement."""
import copy
from knowledge_export import read,canonical
from pathlib import Path

VALUE_UNITS=[{'id':k,'valueKinds':v} for k,v in [('persons',['count']),('years',['age','duration']),('months',['age','duration']),('days',['age','duration']),('sequence',['ordinal']),('camels',['count'])]]
GENERAL={'allowedAssertionClasses':['source_attested','inferred'],'allowedPolarities':['positive','negative','absence_of_evidence'],'allowedModalities':['asserted','possible','conditional','disputed'],'allowedUseTiers':['factual_spine','qualified_context','attributed_disputed_report','not_for_narrative']}
NONFACTUAL=['qualified_context','attributed_disputed_report','not_for_narrative']
EVENTS=['encounter','journey','marriage','birth','death','conversion','participation','narration','pregnancy','purification','grant','blessing','supplication','stoning','pilgrimage','ablution','oath']


def proposal(base,synthetic=False):
    p=copy.deepcopy(base)
    prefix='urn:al-isabah:'+('synthetic:' if synthetic else '')
    e=lambda name:prefix+'event-type:'+name
    p.update(schemaId='al-isabah.knowledge-profile.v2-draft3',version='2.0.0-draft.3',valueUnits=copy.deepcopy(VALUE_UNITS))
    p['id']=prefix+'profile:knowledge-draft3'
    p['realExecutionEnabled']=False;p['realAdmissionEnabled']=False
    p['eventTypes']=list(dict.fromkeys([*p['eventTypes'],*[e(n) for n in EVENTS]]))
    def domain(subjects,objects,entities=(),subject_events=(),object_events=(),kinds=(),units=(),policy=None,rule='none'):
        return {'subjectKinds':list(subjects),'objectKinds':list(objects),'objectEntityKinds':list(entities),'subjectEventTypes':list(subject_events),'objectEventTypes':list(object_events),'objectValueKinds':list(kinds),'objectUnits':list(units),'epistemicPolicy':copy.deepcopy(policy or GENERAL),'sourceEvidenceRule':rule}
    for pred in p['predicates']:
        pred.update(domain(pred['subjectKinds'],pred['objectKinds'],pred['objectEntityKinds'],object_events=p['eventTypes'] if 'events' in pred['objectKinds'] else [],kinds=['count','age','duration','ordinal'] if 'values' in pred['objectKinds'] else [],units=[u['id'] for u in VALUE_UNITS] if 'values' in pred['objectKinds'] else []))
    def add(name,family,**kwargs):
        p['predicates'].append({'id':prefix+'predicate:'+name,'family':family,'directional':True,**domain(**kwargs)})
    def fixed(polarity='positive',modality='asserted'):
        return {'allowedAssertionClasses':['source_attested'],'allowedPolarities':[polarity],'allowedModalities':[modality],'allowedUseTiers':list(NONFACTUAL)}
    for name in ('nursing-sibling-of','foster-parent-of'):add(name,'relationship',subjects=['person'],objects=['entities'],entities=['person'])
    for name in ('companion-status-inferred-from','companion-status-evidence-in','emigrant-status-attested-in'):
        add(name,'source_criticism',subjects=['person'],objects=['sourceRecords'],policy=fixed('absence_of_evidence' if name=='companion-status-evidence-in' else 'positive'),rule='exact_notice_source_author')
    add('precedes','event',subjects=['event'],objects=['events'],subject_events=p['eventTypes'],object_events=p['eventTypes'])
    add('conditioned-on','event',subjects=['event'],objects=['events'],subject_events=p['eventTypes'],object_events=p['eventTypes'],policy=fixed(modality='conditional'))
    add('requests-outcome','event',subjects=['event'],objects=['events'],subject_events=[e('supplication'),e('blessing')],object_events=p['eventTypes'],policy=fixed())
    add('pledged-quantity','event',subjects=['event'],objects=['values'],subject_events=[e('oath')],kinds=['count'],units=['camels'],policy=fixed())
    add('granted-place','event',subjects=['event'],objects=['places'],subject_events=[e('grant')])
    for name in ('departed-from','arrived-at'):add(name,'context',subjects=['event'],objects=['places'],subject_events=[e('journey')])
    p['predicates'].sort(key=lambda x:x['id'])
    return p


if __name__=='__main__':
    import argparse
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    value=proposal(read(root/'profiles/knowledge/volume-08.local-trial.v1.json'))
    path=root/'profiles/knowledge/volume-08.v2-draft3.json';data=canonical(value)
    if args.check:
        if path.read_bytes()!=data:raise SystemExit('draft3-profile-drift')
    else:
        with path.open('xb') as stream:stream.write(data)
    print('draft3-profile-checked' if args.check else 'draft3-profile-written')
