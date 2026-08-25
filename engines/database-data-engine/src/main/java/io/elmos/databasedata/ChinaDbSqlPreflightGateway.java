package io.elmos.databasedata;

import com.fasterxml.jackson.databind.JsonNode;

/** Internal HTTP boundary for the read-only ChinaDB SQL preflight sidecar. */
interface ChinaDbSqlPreflightGateway {
    JsonNode capabilities();

    JsonNode assess(byte[] request, String organizationId, String actorId);
}
