package io.elmos.controlplane;

import com.fasterxml.jackson.databind.JsonNode;

/** Control-plane port to the database-data worker's read-only SQL preflight endpoint. */
interface ChinaDbSqlPreflightGateway {
    JsonNode capabilities();

    JsonNode assess(byte[] request, String organizationId, String actorId);
}
