"""Exact external authorization for provisional local use; never creates approval."""
import datetime
from knowledge_export import digest,shape,reject
from knowledge_local_schema import schema,USES,TIERS

BINDINGS=('snapshotSha256','inventorySha256','profileSha256','schemaSha256','receiptBundleSha256',
          'exportFileSha256','payloadSha256','methodRegistrySha256','sourceRegisterSha256',
          'rightsMatrixSha256','policyBindingSha256','selectedScopeSha256')


def subject(trust):
    return digest({'domain':'al-isabah.local-export-subject.v1','binding':{k:trust[k] for k in BINDINGS}})


def authorization_digest(authorization):
    return digest({'domain':'al-isabah.local-export-authorization.v1','authorization':authorization})


def timestamp(value):
    if not isinstance(value,str):reject('local-authorization-time-invalid')
    shape(value,{'type':'string','pattern':r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$'})
    try:
        result=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
        if result.tzinfo is None:reject('local-authorization-time-invalid')
        return result
    except ValueError:reject('local-authorization-time-invalid')


def validate_authorization(authorization,expected_pin,authority_id,as_of,revoked,payload,trust,requested_use):
    """All operator inputs are external; none is taken from an artifact as authority."""
    definitions=schema();shape(authorization,definitions['$defs']['localAuthorization'],definitions)
    actual=authorization_digest(authorization)
    if not expected_pin or actual!=expected_pin or trust['upstreamAuthorizationSha256']!=actual:reject('local-authorization-pin-mismatch')
    if not authority_id or authorization['authorityId']!=authority_id:reject('local-owner-mismatch')
    if actual in revoked:reject('local-authorization-revoked')
    if authorization['subjectSha256']!=subject(trust):reject('local-authorization-subject-mismatch')
    effective=timestamp(authorization['effectiveAt']);observed=timestamp(authorization['observedAt']);now=timestamp(as_of)
    validity=authorization['validity'];start=timestamp(validity['notBefore'])
    if observed<effective or start<effective or now<start or now<observed:reject('local-authorization-not-current')
    if validity['policy']=='until_revoked':
        if validity['notAfter']!='':reject('local-authorization-time-invalid')
    else:
        end=timestamp(validity['notAfter'])
        if end<=start:reject('local-authorization-time-invalid')
        if now>=end:reject('local-authorization-expired')
    if requested_use not in USES or requested_use not in authorization['allowedUses']:reject('local-use-not-approved')
    if not set(x['tier'] for x in payload['useRestrictions'])<=set(authorization['allowedUseTiers']):reject('local-use-tier-not-approved')
    selection=payload['selection']
    for key in ('requestedLogicalRecordIds','dependencyLogicalRecordIds'):
        if authorization[key]!=selection[key]:reject('local-authorization-scope-mismatch')
    if not authorization['acceptPartial'] and not payload['coverage']['scopeExtractionComplete']:reject('local-partial-not-approved')
    return authorization


def forbid_authorization_cycle(value,authorization_pin):
    """The enclosing authorization is external to every object it authorizes."""
    if isinstance(value,dict):
        if any(k in {'upstreamAuthorizationSha256','authorizationSha256'} for k in value):reject('local-authorization-cycle')
        for child in value.values():forbid_authorization_cycle(child,authorization_pin)
    elif isinstance(value,list):
        for child in value:forbid_authorization_cycle(child,authorization_pin)
    elif authorization_pin and value==authorization_pin:reject('local-authorization-cycle')
