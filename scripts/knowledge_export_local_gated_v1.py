"""Prepare an unadmitted local.1 candidate from a verified gated lineage."""
import copy

import knowledge_export_local as local
import knowledge_local_gated_projection_v1 as gated_projection
from knowledge_export import digest,read,reject,shape,schema_vocabulary
from knowledge_local_schema import SCHEMA,check_semantic_identity
from public_boundary import boundary_errors


def validate_candidate(snapshot,inventory,profile,bundle):
    schema=read(SCHEMA);check_semantic_identity(schema);schema_vocabulary(schema)
    for name,value in [('snapshot',snapshot),('inventory',inventory),('profile',profile)]:
        shape(value,schema['$defs'][name],schema)
        if boundary_errors(value):reject('prohibited-payload')
    if profile!=gated_projection.prior_projection.profile_value():reject('local-profile-not-registered')
    if snapshot['authority']!=profile['authority'] or inventory['authority']!=profile['authority']:
        reject('source-identity-mismatch')
    if inventory['reconciliationStatus'] not in {'verified','fresh_derivation_legacy_mapping_unverified'}:
        reject('source-identity-mismatch')
    if (snapshot['profileSha256']!=digest(profile) or snapshot['inventorySha256']!=digest(inventory)
        or snapshot['receiptBundleSha256']!=digest(bundle)):
        reject('external-pin-mismatch')
    receipts=gated_projection.validate_projection(snapshot,inventory,profile,bundle)
    return local.validate_semantics(snapshot,inventory,profile,bundle,receipts)


def candidate(history,pins,requested,prior_bundle=None):
    snapshot,inventory,profile,bundle=gated_projection.project_history(history,pins,requested,prior_bundle)
    validate_candidate(snapshot,inventory,profile,bundle)
    payload=local.payload_value(snapshot,inventory)
    bindings=local.bindings_value(snapshot,inventory,profile,bundle,payload)
    request={'schema':'al-isabah.knowledge-local-authorization-request.v1',
             'subjectSha256':local.subject(bindings),'bindings':bindings,
             'requestedLogicalRecordIds':payload['selection']['requestedLogicalRecordIds'],
             'dependencyLogicalRecordIds':payload['selection']['dependencyLogicalRecordIds'],
             'coverage':copy.deepcopy(payload['coverage']),
             'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False}
    return snapshot,inventory,profile,bundle,payload,bindings,request
