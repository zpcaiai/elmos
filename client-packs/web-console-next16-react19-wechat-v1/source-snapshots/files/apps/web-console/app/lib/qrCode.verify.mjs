/**
 * qrCode.ts 的正确性验证。
 *
 * 二维码这种东西"看起来像"没有任何意义——一张画错的码依然是一张方方正正的黑白图，
 * 肉眼分辨不出来，而用户会去扫它。所以这里用两种互相独立的判据：
 *
 *   A. 逐模块比对成熟参考实现（Python `qrcode`），26 段文本 × 8 个掩码，覆盖版本 1–10。
 *      这验证编码、纠错、分块交错、模块布局、格式信息在每个掩码下都逐位一致。
 *
 *   B. 用真实扫描器（OpenCV QRCodeDetector）解码，断言读回原文。
 *      这验证"扫得出来"，而不只是"和参考实现一样"。
 *
 * 只有 A 不够：两边可能一起错（虽然不太可能）。
 * 只有 B 不够：检测器对某些掩码有识别局限，通过不代表编码对。
 *
 * 用法（需要 python3 + qrcode + opencv-python-headless）：
 *   node --experimental-strip-types qrCode.verify.mjs
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { encodeQrMatrix, renderQrSvg } from "./qrCode.ts";

const work = mkdtempSync(join(tmpdir(), "qr-verify-"));
let exitCode = 0;

const CASES = [
  "weixin://wxpay/bizpayurl?pr=abcdefg",
  "weixin://wxpay/bizpayurl?pr=x1Y2z3A4b5",
  "A",
  "hello world",
];
// 覆盖每个版本的容量边界：跨过边界的那一字节最容易触发分块与补位的错误
for (const n of [1, 14, 15, 16, 26, 27, 42, 43, 62, 63, 84, 85, 106, 107, 122, 123, 152, 153, 180, 181, 213]) {
  CASES.push(Array.from({ length: n }, (_, i) => "abcdefghijklmnopqrstuvwxyz0123456789-_:/?=."[(i * 7 + 3) % 42]).join(""));
}

const REFERENCE_SCRIPT = `
import json, sys, numpy as np, cv2, qrcode
from qrcode.constants import ERROR_CORRECT_M
from qrcode.util import QRData, MODE_8BIT_BYTE

job = json.load(sys.stdin)

reference = []
for text in job["texts"]:
    for mask in range(8):
        q = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=0, box_size=1, mask_pattern=mask)
        q.add_data(QRData(text.encode("utf-8"), mode=MODE_8BIT_BYTE))
        q.make(fit=True)
        reference.append({"text": text, "mask": mask, "version": q.version,
                          "modules": ["".join("1" if v else "0" for v in row) for row in q.get_matrix()]})

decoded = []
detector = cv2.QRCodeDetector()
for item in job["mine"]:
    m = np.array([[0 if c == "1" else 255 for c in row] for row in item["modules"]], dtype=np.uint8)
    padded = np.full((m.shape[0] + 8, m.shape[1] + 8), 255, np.uint8)
    padded[4:4 + m.shape[0], 4:4 + m.shape[1]] = m
    image = np.kron(padded, np.ones((8, 8), np.uint8))
    text, _, _ = detector.detectAndDecode(image)
    decoded.append(text)

json.dump({"reference": reference, "decoded": decoded}, sys.stdout)
`;

const mine = CASES.map((text) => ({
  text,
  modules: encodeQrMatrix(text).map((row) => row.map((v) => (v ? "1" : "0")).join("")),
}));

const scriptPath = join(work, "reference.py");
writeFileSync(scriptPath, REFERENCE_SCRIPT);

let result;
try {
  const stdout = execFileSync("python3", [scriptPath], {
    input: JSON.stringify({ texts: CASES, mine }),
    maxBuffer: 64 * 1024 * 1024,
  });
  result = JSON.parse(stdout.toString());
} catch (error) {
  console.log("NOT_RUN: 参考实现不可用（需要 python3 + qrcode + opencv-python-headless）");
  console.log("         这不等于通过。");
  rmSync(work, { recursive: true, force: true });
  process.exit(3);
}

// --- A. 逐模块比对 ---------------------------------------------------------
// 强制掩码后比对，把"掩码选择"这个纯启发式的差异排除在外：
// 掩码选得不同不影响码的合法性，编码错了才影响。
let matched = 0;
const mismatches = [];
for (const item of result.reference) {
  const rows = encodeQrMatrix(item.text, item.mask)
    .map((row) => row.map((v) => (v ? "1" : "0")).join(""));
  const same = rows.length === item.modules.length && rows.every((r, i) => r === item.modules[i]);
  if (same) matched += 1;
  else mismatches.push(`v${item.version} len=${item.text.length} mask=${item.mask}`);
}
console.log(`A. 逐模块比对参考实现：${matched}/${result.reference.length} 一致`);
for (const m of mismatches.slice(0, 10)) console.log(`   [FAIL] ${m}`);
if (mismatches.length) exitCode = 1;

// --- B. 真实扫描器解码 ------------------------------------------------------
let decodedOk = 0;
const undecodable = [];
result.decoded.forEach((text, index) => {
  if (text === CASES[index]) decodedOk += 1;
  else undecodable.push(`len=${CASES[index].length}`);
});
console.log(`B. OpenCV 解码回原文：${decodedOk}/${CASES.length} 通过`);
for (const u of undecodable.slice(0, 10)) console.log(`   [FAIL] ${u}`);
if (undecodable.length) exitCode = 1;

// --- C. SVG 渲染的基本约束 --------------------------------------------------
const svg = renderQrSvg("weixin://wxpay/bizpayurl?pr=abcdefghij");
const svgChecks = [
  ["是自包含 SVG", svg.startsWith("<svg") && svg.endsWith("</svg>")],
  ["带 viewBox（可任意缩放而不失真）", svg.includes("viewBox=")],
  ["用 crispEdges（缩放时不做抗锯齿，否则边缘发灰会扫不出）",
    svg.includes('shape-rendering="crispEdges"')],
  ["白底显式声明（透明底在深色主题下会反色，直接扫不出）", svg.includes('fill="#ffffff"')],
  ["静区小于 4 时拒绝渲染", (() => {
    try { renderQrSvg("x", 3); return false; } catch { return true; }
  })()],
  ["空内容拒绝渲染", (() => {
    try { renderQrSvg(""); return false; } catch { return true; }
  })()],
  ["超出版本 10 容量时抛错而不是截断", (() => {
    try { renderQrSvg("x".repeat(400)); return false; } catch { return true; }
  })()],
];
let svgOk = 0;
for (const [what, ok] of svgChecks) {
  if (ok) { svgOk += 1; } else { console.log(`   [FAIL] ${what}`); exitCode = 1; }
}
console.log(`C. SVG 渲染约束：${svgOk}/${svgChecks.length} 通过`);

rmSync(work, { recursive: true, force: true });
console.log(exitCode === 0 ? "\n全部通过" : "\n有失败项");
process.exit(exitCode);
