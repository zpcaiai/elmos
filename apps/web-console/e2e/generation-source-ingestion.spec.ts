import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import {
  buildGenerationSourceBundle,
  generationSourceIngestionTestHooks as hooks,
  sourceIngestionError,
} from "../app/lib/server/generationSourceIngestion";

function upload(name: string, raw: Buffer, declaredSize = raw.byteLength) {
  return {
    name,
    type: "application/octet-stream",
    size: declaredSize,
    async arrayBuffer() {
      return Uint8Array.from(raw).buffer;
    },
  };
}

async function expectSourceError(
  action: () => Promise<unknown>,
  status: number,
  reason: string,
) {
  await expect(action()).rejects.toThrow(reason);
  try {
    await action();
  } catch (error) {
    expect(sourceIngestionError(error)).toEqual({ status, reason });
  }
}

test.describe("generation source ingestion security and parser qualification", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "deterministic server qualification runs once");
  });

  test("accepts supported text formats and strips executable HTML content", async () => {
    const cases = [
      ["requirements.txt", Buffer.from("plain requirements"), "text-file"],
      ["requirements.md", Buffer.from("# Markdown\nrequirements"), "markdown-file"],
      [
        "requirements.html",
        Buffer.from("<main>safe requirement<script>secret()</script><style>.x{}</style></main>"),
        "html-file",
      ],
    ] as const;

    for (const [name, raw, kind] of cases) {
      const extracted = await hooks.extractUploadedSource(upload(name, raw));
      expect(extracted.kind).toBe(kind);
      expect(extracted.text).toContain("requirement");
      expect(extracted.text).not.toContain("secret()");
      expect(extracted.text).not.toContain(".x{}");
    }
  });

  test("rejects malformed, oversized, mismatched, legacy, and unsupported uploads", async () => {
    await expectSourceError(
      () => hooks.extractUploadedSource(upload("empty.txt", Buffer.alloc(0))),
      413,
      "SOURCE_FILE_SIZE_INVALID",
    );
    await expectSourceError(
      () => hooks.extractUploadedSource(upload("large.txt", Buffer.from("small"), hooks.limits.maxFileBytes + 1)),
      413,
      "SOURCE_FILE_SIZE_INVALID",
    );
    await expectSourceError(
      () => hooks.extractUploadedSource(upload("mismatch.txt", Buffer.from("abc"), 4)),
      413,
      "SOURCE_FILE_SIZE_MISMATCH",
    );
    await expectSourceError(
      () => hooks.extractUploadedSource(upload("invalid.txt", Buffer.from([0xc3, 0x28]))),
      422,
      "SOURCE_TEXT_MUST_BE_UTF8",
    );
    await expectSourceError(
      () => hooks.extractUploadedSource(upload("legacy.doc", Buffer.from("legacy"))),
      415,
      "LEGACY_DOC_UNSUPPORTED_CONVERT_TO_DOCX",
    );
    await expectSourceError(
      () => hooks.extractUploadedSource(upload("archive.zip", Buffer.from("archive"))),
      415,
      "SOURCE_FILE_TYPE_UNSUPPORTED",
    );
    await expectSourceError(
      () => hooks.extractUploadedSource(upload("blank.md", Buffer.from(" \n "))),
      422,
      "SOURCE_TEXT_EMPTY",
    );
  });

  test("blocks private, loopback, link-local, documentation, multicast, and mapped addresses", () => {
    const blocked = [
      ["0.0.0.0", 4],
      ["10.0.0.1", 4],
      ["100.64.0.1", 4],
      ["127.0.0.1", 4],
      ["169.254.169.254", 4],
      ["172.16.0.1", 4],
      ["192.168.1.1", 4],
      ["198.18.0.1", 4],
      ["198.51.100.1", 4],
      ["203.0.113.1", 4],
      ["224.0.0.1", 4],
      ["::", 6],
      ["::1", 6],
      ["fc00::1", 6],
      ["fe80::1", 6],
      ["ff02::1", 6],
      ["2001:db8::1", 6],
      ["::ffff:127.0.0.1", 6],
    ] as const;
    for (const [address, family] of blocked) {
      expect(hooks.isPublicAddress(address, family), address).toBe(false);
    }
    expect(hooks.isPublicAddress("8.8.8.8", 4)).toBe(true);
    expect(hooks.isPublicAddress("2606:4700:4700::1111", 6)).toBe(true);
  });

  test("sanitizes labels and never preserves credentials, query, or fragments in origins", () => {
    expect(hooks.safeLabel("../../requirements.md")).toBe("requirements.md");
    expect(() => hooks.safeLabel("\u0000")).toThrow("SOURCE_LABEL_INVALID");
    const origin = hooks.publicOrigin(
      new URL("https://user:secret@example.com/docs?q=token#private"),
    );
    expect(origin).toBe("https://example.com/docs");
  });

  test("enforces source counts and deterministic truncation with digest-bound references", async () => {
    const tooManyFiles = Array.from(
      { length: hooks.limits.maxFiles + 1 },
      (_, index) => upload(`source-${index}.txt`, Buffer.from("requirement")),
    );
    await expectSourceError(
      () => buildGenerationSourceBundle({
        files: tooManyFiles,
        repositoryRoot: process.cwd(),
      }),
      413,
      "SOURCE_FILE_COUNT_EXCEEDED",
    );

    const long = "r".repeat(hooks.limits.maxSourceCharacters + 1);
    const first = await buildGenerationSourceBundle({
      description: long,
      repositoryRoot: process.cwd(),
    });
    const second = await buildGenerationSourceBundle({
      description: long,
      repositoryRoot: process.cwd(),
    });
    expect(first.sources[0]).toMatchObject({
      id: "SRC-001",
      truncated: true,
      extractedCharacters: long.length,
    });
    expect(first.sources[0].sha256).toBe(second.sources[0].sha256);
    expect(first.bundleSha256).toBe(second.bundleSha256);
    expect(first.combinedText.length).toBeLessThanOrEqual(hooks.limits.maxCombinedCharacters);
  });

  test("imports Skill text as untrusted requirements and blocks traversal and symlinks", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "elmos-source-skill-"));
    try {
      const skillDir = path.join(root, ".agents", "skills", "safe-skill");
      await mkdir(skillDir, { recursive: true });
      await writeFile(path.join(skillDir, "SKILL.md"), "# Safe Skill\nGenerate an API.");
      const bundle = await buildGenerationSourceBundle({
        skillNames: ["safe-skill"],
        repositoryRoot: root,
      });
      expect(bundle.sources[0]).toMatchObject({
        kind: "skill",
        label: "safe-skill",
        warnings: ["SKILL_IMPORTED_AS_UNTRUSTED_REQUIREMENTS_NOT_EXECUTED"],
      });

      await expectSourceError(
        () => buildGenerationSourceBundle({
          skillNames: ["../escape"],
          repositoryRoot: root,
        }),
        400,
        "SOURCE_SKILL_NAME_INVALID",
      );

      const outside = path.join(root, "outside.md");
      await writeFile(outside, "# Outside\nmust not load");
      const linkedDir = path.join(root, ".agents", "skills", "linked-skill");
      await mkdir(linkedDir, { recursive: true });
      await symlink(outside, path.join(linkedDir, "SKILL.md"));
      await expectSourceError(
        () => buildGenerationSourceBundle({
          skillNames: ["linked-skill"],
          repositoryRoot: root,
        }),
        400,
        "SOURCE_SKILL_PATH_UNSAFE",
      );
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("normalization is idempotent across a deterministic fuzz corpus", () => {
    let state = 0x5eed1234;
    const next = () => {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
      return state;
    };
    const alphabet = ["a", " ", "\t", "\r", "\n", "\u0000", "\u0007", "中", "🙂"];
    for (let caseIndex = 0; caseIndex < 256; caseIndex += 1) {
      let candidate = "";
      const length = next() % 512;
      for (let index = 0; index < length; index += 1) {
        candidate += alphabet[next() % alphabet.length];
      }
      const normalized = hooks.normalizeText(candidate);
      expect(hooks.normalizeText(normalized)).toBe(normalized);
      expect(normalized).not.toMatch(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/);
    }
  });

  test("independent negative controls kill seeded boundary mutants", () => {
    const privateAddressCorpus = [
      ["127.0.0.1", 4],
      ["169.254.169.254", 4],
      ["::1", 6],
    ] as const;
    const mutants = [
      {
        id: "MUTANT_ALLOW_ALL_IPV4",
        policy: (_address: string, family: number) => family === 4,
      },
      {
        id: "MUTANT_ALLOW_LOOPBACK_V6",
        policy: (address: string, family: number) => (
          family === 6 && (address === "::1" || hooks.isPublicAddress(address, family))
        ),
      },
    ];

    for (const mutant of mutants) {
      const killed = privateAddressCorpus.some(
        ([address, family]) => mutant.policy(address, family),
      );
      expect(killed, `${mutant.id} survived the negative corpus`).toBe(true);
    }
  });

  test("independent holdout and representative corpora preserve exact policy outcomes", async () => {
    const corpusRoot = path.resolve(
      __dirname,
      "../../../verification-packs/elmos-project-generation-source-ingestion/corpus",
    );
    const holdout = JSON.parse(
      await readFile(path.join(corpusRoot, "holdout/cases.json"), "utf8"),
    ) as {
      addresses: Array<{ address: string; family: number; public: boolean }>;
      labels: Array<{ input: string; expected: string }>;
    };
    for (const item of holdout.addresses) {
      expect(hooks.isPublicAddress(item.address, item.family), item.address).toBe(item.public);
    }
    for (const item of holdout.labels) {
      expect(hooks.safeLabel(item.input)).toBe(item.expected);
    }

    const representative = JSON.parse(
      await readFile(path.join(corpusRoot, "representative-workloads/cases.json"), "utf8"),
    ) as {
      workloads: Array<{
        description: string;
        expected_source_count: number;
      }>;
    };
    for (const workload of representative.workloads) {
      const bundle = await buildGenerationSourceBundle({
        description: workload.description,
        repositoryRoot: process.cwd(),
      });
      expect(bundle.status).toBe("READY_FOR_REVIEW");
      expect(bundle.sources).toHaveLength(workload.expected_source_count);
      expect(bundle.bundleSha256).toMatch(/^[a-f0-9]{64}$/);
    }
  });
});
