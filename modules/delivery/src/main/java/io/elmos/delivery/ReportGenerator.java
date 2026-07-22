package io.elmos.delivery;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.delivery.DeliveryModels.*;

import java.util.Comparator;

public final class ReportGenerator {
    private final DeliveryReadModel readModel;
    public ReportGenerator(ObjectMapper json) { this.readModel = new DeliveryReadModel(json); }

    public ReportBundle generate(DeliverySnapshot snapshot) {
        String authoritative = readModel.write(snapshot);
        StringBuilder markdown = new StringBuilder("# ELMOS Migration Delivery\n\n")
                .append("- Migration: `").append(snapshot.migrationId()).append("`\n")
                .append("- HEAD: `").append(snapshot.deliveryHeadSha()).append("`\n")
                .append("- Status: **").append(snapshot.status()).append("**\n")
                .append("- Validation: **").append(snapshot.validationStatus()).append("**\n\n## Evidence facts\n\n");
        snapshot.facts().stream().sorted(Comparator.comparing(EvidenceFact::factId)).forEach(fact -> markdown
                .append("- ").append(escapeMarkdown(fact.domain())).append(" / ").append(escapeMarkdown(fact.status()))
                .append(": ").append(escapeMarkdown(fact.summary())).append("\n"));
        markdown.append("\n## Risks\n\n");
        snapshot.risks().stream().sorted(Comparator.comparing(RiskItem::riskId)).forEach(risk -> markdown
                .append("- ").append(risk.severity()).append(" / ").append(risk.status()).append(": ")
                .append(escapeMarkdown(risk.title())).append("\n"));
        String html = "<!doctype html><html><head><meta charset=\"utf-8\"><title>ELMOS Delivery</title></head><body>"
                + "<h1>ELMOS Migration Delivery</h1><dl><dt>Migration</dt><dd>" + html(snapshot.migrationId())
                + "</dd><dt>HEAD</dt><dd>" + html(snapshot.deliveryHeadSha()) + "</dd><dt>Status</dt><dd>" + snapshot.status()
                + "</dd><dt>Validation</dt><dd>" + snapshot.validationStatus() + "</dd></dl><h2>Evidence facts</h2><ul>"
                + snapshot.facts().stream().sorted(Comparator.comparing(EvidenceFact::factId))
                .map(fact -> "<li>" + html(fact.domain()) + " / " + html(fact.status()) + ": " + html(fact.summary()) + "</li>").reduce("", String::concat)
                + "</ul><h2>Risks</h2><ul>" + snapshot.risks().stream().sorted(Comparator.comparing(RiskItem::riskId))
                .map(risk -> "<li>" + risk.severity() + " / " + risk.status() + ": " + html(risk.title()) + "</li>").reduce("", String::concat)
                + "</ul></body></html>";
        return new ReportBundle(authoritative, markdown.toString(), html, DeliveryReadModel.hash(authoritative));
    }

    private static String escapeMarkdown(String value) { return value.replace("\\", "\\\\").replace("`", "\\`").replace("*", "\\*"); }
    private static String html(String value) { return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&#39;"); }
}
