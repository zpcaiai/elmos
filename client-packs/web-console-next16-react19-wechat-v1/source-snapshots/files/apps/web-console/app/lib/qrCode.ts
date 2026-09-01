/**
 * 最小 QR 码编码器 —— 只为渲染微信支付 Native 的 `code_url`。
 *
 * 为什么不装 `qrcode` 这个包：微信 Native 支付要求商户自行把 `code_url`
 * 渲染成二维码给用户扫。这是收款链路上的一环，不能因为"缺个前端依赖"就断掉。
 * 但往 web-console 里加一个运行时依赖是仓库主人的决定，不该由一次改动顺手做掉。
 * 因此这里放一个**范围严格收窄**的实现：
 *
 *   - 只支持字节模式（`code_url` 是 `weixin://wxpay/bizpayurl?pr=...`，ASCII）
 *   - 只支持纠错级别 M（微信官方示例用的级别）
 *   - 只支持版本 1–10（足够到 213 字节，`code_url` 一般 40 字节上下）
 *
 * 超出范围一律抛错，不做静默降级：一个渲染错的二维码比没有二维码更糟——
 * 用户会扫，然后付到别处或者付失败，而我们这边看不出任何异常。
 *
 * 正确性不是靠"看起来对"：`qrCode.verify.mjs` 把本文件的输出与 Python
 * `qrcode` 库（成熟的参考实现）逐模块比对，覆盖多种长度与内容。
 */

/** 纠错级别 M 的版本参数：[总码字, 每块纠错码字, 组1块数, 组1数据码字, 组2块数, 组2数据码字] */
const VERSION_TABLE_M: readonly (readonly number[])[] = [
  [26, 10, 1, 16, 0, 0], // v1
  [44, 16, 1, 28, 0, 0], // v2
  [70, 26, 1, 44, 0, 0], // v3
  [100, 18, 2, 32, 0, 0], // v4
  [134, 24, 2, 43, 0, 0], // v5
  [172, 16, 4, 27, 0, 0], // v6
  [196, 18, 4, 31, 0, 0], // v7
  [242, 22, 2, 38, 2, 39], // v8
  [292, 22, 3, 36, 2, 37], // v9
  [346, 26, 4, 43, 1, 44], // v10
];

/** 各版本的对齐图案中心坐标。v1 没有对齐图案。 */
const ALIGNMENT_CENTERS: readonly (readonly number[])[] = [
  [], [6, 18], [6, 22], [6, 26], [6, 30],
  [6, 34], [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50],
];

const MAX_VERSION = 10;

// ---------------------------------------------------------------------------
// GF(256) —— QR 用的本原多项式是 0x11d
// ---------------------------------------------------------------------------

const EXP = new Uint8Array(512);
const LOG = new Uint8Array(256);
(function buildGaloisTables() {
  let x = 1;
  for (let i = 0; i < 255; i += 1) {
    EXP[i] = x;
    LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
  }
  for (let i = 255; i < 512; i += 1) EXP[i] = EXP[i - 255];
})();

function gfMultiply(a: number, b: number): number {
  if (a === 0 || b === 0) return 0;
  return EXP[LOG[a] + LOG[b]];
}

/** 纠错码字数为 degree 的生成多项式。 */
function generatorPolynomial(degree: number): number[] {
  let poly = [1];
  for (let i = 0; i < degree; i += 1) {
    const next = new Array<number>(poly.length + 1).fill(0);
    for (let j = 0; j < poly.length; j += 1) {
      next[j] ^= poly[j];
      next[j + 1] ^= gfMultiply(poly[j], EXP[i]);
    }
    poly = next;
  }
  return poly;
}

function errorCorrection(data: readonly number[], ecLength: number): number[] {
  const generator = generatorPolynomial(ecLength);
  const remainder = new Array<number>(ecLength).fill(0);
  for (const byte of data) {
    const factor = byte ^ remainder[0];
    remainder.shift();
    remainder.push(0);
    if (factor !== 0) {
      for (let i = 0; i < ecLength; i += 1) {
        remainder[i] ^= gfMultiply(generator[i + 1], factor);
      }
    }
  }
  return remainder;
}

// ---------------------------------------------------------------------------
// 数据编码
// ---------------------------------------------------------------------------

class BitBuffer {
  private readonly bits: number[] = [];

  push(value: number, length: number): void {
    for (let i = length - 1; i >= 0; i -= 1) {
      this.bits.push((value >>> i) & 1);
    }
  }

  get length(): number {
    return this.bits.length;
  }

  toBytes(): number[] {
    const bytes: number[] = [];
    for (let i = 0; i < this.bits.length; i += 8) {
      let byte = 0;
      for (let j = 0; j < 8; j += 1) {
        byte = (byte << 1) | (this.bits[i + j] ?? 0);
      }
      bytes.push(byte);
    }
    return bytes;
  }
}

function dataCodewordCount(version: number): number {
  const [, ecPerBlock, blocks1, data1, blocks2, data2] = VERSION_TABLE_M[version - 1];
  void ecPerBlock;
  return blocks1 * data1 + blocks2 * data2;
}

/** 字符计数指示符位宽：字节模式下 v1–9 是 8 位，v10 起是 16 位。 */
function characterCountBits(version: number): number {
  return version < 10 ? 8 : 16;
}

function chooseVersion(byteLength: number): number {
  for (let version = 1; version <= MAX_VERSION; version += 1) {
    const capacityBits = dataCodewordCount(version) * 8;
    const neededBits = 4 + characterCountBits(version) + byteLength * 8;
    if (neededBits <= capacityBits) return version;
  }
  throw new Error(
    `QR_PAYLOAD_TOO_LONG: ${byteLength} 字节超出本实现支持的版本 1–10（纠错级别 M）`,
  );
}

function encodePayload(bytes: readonly number[], version: number): number[] {
  const buffer = new BitBuffer();
  buffer.push(0b0100, 4); // 字节模式
  buffer.push(bytes.length, characterCountBits(version));
  for (const byte of bytes) buffer.push(byte, 8);

  const capacityBits = dataCodewordCount(version) * 8;
  // 终止符最多 4 位，容量不足时截短
  buffer.push(0, Math.min(4, capacityBits - buffer.length));
  // 补到字节边界
  if (buffer.length % 8 !== 0) buffer.push(0, 8 - (buffer.length % 8));

  const codewords = buffer.toBytes();
  const padBytes = [0xec, 0x11];
  let padIndex = 0;
  while (codewords.length < dataCodewordCount(version)) {
    codewords.push(padBytes[padIndex % 2]);
    padIndex += 1;
  }
  return codewords;
}

/** 按块切分、各自算纠错码，再按 QR 规定的顺序交错。 */
function interleave(codewords: readonly number[], version: number): number[] {
  const [, ecPerBlock, blocks1, data1, blocks2, data2] = VERSION_TABLE_M[version - 1];
  const dataBlocks: number[][] = [];
  const ecBlocks: number[][] = [];

  let offset = 0;
  for (let i = 0; i < blocks1; i += 1) {
    const block = codewords.slice(offset, offset + data1);
    offset += data1;
    dataBlocks.push(block);
    ecBlocks.push(errorCorrection(block, ecPerBlock));
  }
  for (let i = 0; i < blocks2; i += 1) {
    const block = codewords.slice(offset, offset + data2);
    offset += data2;
    dataBlocks.push(block);
    ecBlocks.push(errorCorrection(block, ecPerBlock));
  }

  const result: number[] = [];
  const maxData = Math.max(data1, data2);
  for (let i = 0; i < maxData; i += 1) {
    for (const block of dataBlocks) {
      if (i < block.length) result.push(block[i]);
    }
  }
  for (let i = 0; i < ecPerBlock; i += 1) {
    for (const block of ecBlocks) result.push(block[i]);
  }
  return result;
}

// ---------------------------------------------------------------------------
// 矩阵布局
// ---------------------------------------------------------------------------

type Matrix = {
  size: number;
  modules: (boolean | null)[][];
  reserved: boolean[][];
};

function emptyMatrix(version: number): Matrix {
  const size = version * 4 + 17;
  return {
    size,
    modules: Array.from({ length: size }, () => new Array<boolean | null>(size).fill(null)),
    reserved: Array.from({ length: size }, () => new Array<boolean>(size).fill(false)),
  };
}

function setFunction(matrix: Matrix, row: number, column: number, dark: boolean): void {
  matrix.modules[row][column] = dark;
  matrix.reserved[row][column] = true;
}

function placeFinder(matrix: Matrix, row: number, column: number): void {
  // 含分隔符：7×7 图案外再留一圈浅色
  for (let r = -1; r <= 7; r += 1) {
    for (let c = -1; c <= 7; c += 1) {
      const y = row + r;
      const x = column + c;
      if (y < 0 || y >= matrix.size || x < 0 || x >= matrix.size) continue;
      const onBorder = (r >= 0 && r <= 6 && (c === 0 || c === 6))
        || (c >= 0 && c <= 6 && (r === 0 || r === 6));
      const inCore = r >= 2 && r <= 4 && c >= 2 && c <= 4;
      setFunction(matrix, y, x, onBorder || inCore);
    }
  }
}

function placeAlignment(matrix: Matrix, version: number): void {
  const centers = ALIGNMENT_CENTERS[version - 1];
  for (const row of centers) {
    for (const column of centers) {
      // 与定位图案重叠的三个角要跳过
      const overlapsFinder = (row <= 8 && column <= 8)
        || (row <= 8 && column >= matrix.size - 9)
        || (row >= matrix.size - 9 && column <= 8);
      if (overlapsFinder) continue;
      for (let r = -2; r <= 2; r += 1) {
        for (let c = -2; c <= 2; c += 1) {
          const dark = Math.max(Math.abs(r), Math.abs(c)) !== 1;
          setFunction(matrix, row + r, column + c, dark);
        }
      }
    }
  }
}

function placeTiming(matrix: Matrix): void {
  for (let i = 8; i < matrix.size - 8; i += 1) {
    const dark = i % 2 === 0;
    if (!matrix.reserved[6][i]) setFunction(matrix, 6, i, dark);
    if (!matrix.reserved[i][6]) setFunction(matrix, i, 6, dark);
  }
}

/** 预留格式信息区（内容在选定掩码后再写）。 */
function reserveFormatArea(matrix: Matrix): void {
  for (let i = 0; i <= 8; i += 1) {
    if (!matrix.reserved[8][i]) setFunction(matrix, 8, i, false);
    if (!matrix.reserved[i][8]) setFunction(matrix, i, 8, false);
  }
  for (let i = 0; i < 8; i += 1) {
    setFunction(matrix, 8, matrix.size - 1 - i, false);
    setFunction(matrix, matrix.size - 1 - i, 8, false);
  }
  // 固定的暗模块
  setFunction(matrix, matrix.size - 8, 8, true);
}

function reserveVersionArea(matrix: Matrix, version: number): void {
  if (version < 7) return;
  for (let i = 0; i < 18; i += 1) {
    const row = Math.floor(i / 3);
    const column = matrix.size - 11 + (i % 3);
    setFunction(matrix, row, column, false);
    setFunction(matrix, column, row, false);
  }
}

function placeData(matrix: Matrix, codewords: readonly number[]): void {
  let bitIndex = 0;
  let upward = true;
  for (let right = matrix.size - 1; right >= 1; right -= 2) {
    // 第 6 列是竖直定时图案，整列跳过。
    //
    // 这里必须**改写循环变量本身**，不能只在本轮换一个列号：
    // 跳过后剩下的列对应当是 (5,4) (3,2) (1,0)；若只在本轮用 5 而 right 仍是 6，
    // 下一轮就变成 (4,3) (2,1)，左半边的数据位全部错位。
    // 这个 bug 的表现极具迷惑性——码是能画出来的，结构、定位图案、
    // 大部分模块都对，只有左侧十几个模块不同，肉眼完全看不出来，
    // 扫出来则是校验失败或乱码。是逐模块比对参考实现才抓到的。
    if (right === 6) right = 5;
    for (let step = 0; step < matrix.size; step += 1) {
      const row = upward ? matrix.size - 1 - step : step;
      for (const column of [right, right - 1]) {
        if (matrix.reserved[row][column]) continue;
        const byte = codewords[bitIndex >>> 3] ?? 0;
        const bit = (byte >>> (7 - (bitIndex & 7))) & 1;
        matrix.modules[row][column] = bit === 1;
        bitIndex += 1;
      }
    }
    upward = !upward;
  }
}

const MASK_PREDICATES: readonly ((row: number, column: number) => boolean)[] = [
  (r, c) => (r + c) % 2 === 0,
  (r) => r % 2 === 0,
  (_r, c) => c % 3 === 0,
  (r, c) => (r + c) % 3 === 0,
  (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0,
  (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
  (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0,
  (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0,
];

function applyMask(matrix: Matrix, mask: number): boolean[][] {
  const predicate = MASK_PREDICATES[mask];
  return matrix.modules.map((row, r) =>
    row.map((value, c) => {
      const dark = value === true;
      if (matrix.reserved[r][c]) return dark;
      return predicate(r, c) ? !dark : dark;
    }),
  );
}

/** 标准的四条罚分规则。分数越低越好。 */
function penalty(modules: readonly (readonly boolean[])[]): number {
  const size = modules.length;
  let score = 0;

  // 规则 1：同色连续 5 个以上
  for (let i = 0; i < size; i += 1) {
    for (const horizontal of [true, false]) {
      let run = 1;
      for (let j = 1; j < size; j += 1) {
        const current = horizontal ? modules[i][j] : modules[j][i];
        const previous = horizontal ? modules[i][j - 1] : modules[j - 1][i];
        if (current === previous) {
          run += 1;
        } else {
          if (run >= 5) score += run - 2;
          run = 1;
        }
      }
      if (run >= 5) score += run - 2;
    }
  }

  // 规则 2：2×2 同色方块
  for (let r = 0; r < size - 1; r += 1) {
    for (let c = 0; c < size - 1; c += 1) {
      const v = modules[r][c];
      if (v === modules[r][c + 1] && v === modules[r + 1][c] && v === modules[r + 1][c + 1]) {
        score += 3;
      }
    }
  }

  // 规则 3：形似定位图案的 1:1:3:1:1 序列
  const patternA = [true, false, true, true, true, false, true, false, false, false, false];
  const patternB = [false, false, false, false, true, false, true, true, true, false, true];
  const matches = (line: readonly boolean[], start: number, pattern: readonly boolean[]) => {
    for (let i = 0; i < pattern.length; i += 1) {
      if (line[start + i] !== pattern[i]) return false;
    }
    return true;
  };
  // 两端各补 4 个浅色模块再匹配：规范里这条规则说的是
  // "1:1:3:1:1 图案的一侧有宽度 4 的浅色区"，而符号边界外就是静区（浅色）。
  // 不补的话，紧贴边缘的伪定位图案会被漏掉——它恰恰是最容易被扫描器误认的位置。
  const quiet = [false, false, false, false];
  for (let i = 0; i < size; i += 1) {
    const row = [...quiet, ...modules[i], ...quiet];
    const column = [...quiet, ...modules.map((line) => line[i]), ...quiet];
    for (let j = 0; j + 11 <= row.length; j += 1) {
      if (matches(row, j, patternA) || matches(row, j, patternB)) score += 40;
      if (matches(column, j, patternA) || matches(column, j, patternB)) score += 40;
    }
  }

  // 规则 4：深色模块占比偏离 50%
  let dark = 0;
  for (const row of modules) for (const value of row) if (value) dark += 1;
  const percent = (dark * 100) / (size * size);
  score += Math.floor(Math.abs(percent - 50) / 5) * 10;

  return score;
}

/** 格式信息：5 位数据 + BCH(15,5)，再与 0x5412 异或。级别 M 的指示位是 0b00。 */
function formatBits(mask: number): number {
  const data = (0b00 << 3) | mask;
  let value = data << 10;
  for (let i = 4; i >= 0; i -= 1) {
    if ((value >>> (i + 10)) & 1) value ^= 0x537 << i;
  }
  return ((data << 10) | value) ^ 0x5412;
}

/**
 * 写入两份格式信息。
 *
 * <p><b>坐标顺序在这里踩过一次坑，值得写下来。</b>常被引用的参考实现
 * （nayuki 的 QrCode.java）里这段是 {@code setFunctionModule(8, i, bit)}，
 * 而那个方法的签名是 {@code (x, y)} —— 也就是 {@code modules[y][x]}，
 * 即"第 i 行、第 8 列"。照字面当成 {@code (row, col)} 抄下来就会整体转置，
 * 结果是：定位图案、时序、数据全对，只有格式信息那 31 个模块镜像了。
 * 扫描器读到的纠错级别与掩码号是错的，于是整张码解不出来——
 * 而肉眼看上去它就是一张正常的二维码。
 *
 * <p>本函数按「行、列」明确写出，不再依赖对参考实现参数序的记忆。
 */
function placeFormat(modules: boolean[][], mask: number): void {
  const size = modules.length;
  const bits = formatBits(mask);
  const bitAt = (index: number) => ((bits >>> index) & 1) === 1;

  // 第一份：左上角，竖直段在第 8 列，水平段在第 8 行
  for (let i = 0; i <= 5; i += 1) modules[i][8] = bitAt(i);
  modules[7][8] = bitAt(6);
  modules[8][8] = bitAt(7);
  modules[8][7] = bitAt(8);
  for (let i = 9; i <= 14; i += 1) modules[8][14 - i] = bitAt(i);

  // 第二份：右上（第 8 行）与左下（第 8 列）
  for (let i = 0; i <= 7; i += 1) modules[8][size - 1 - i] = bitAt(i);
  for (let i = 8; i <= 14; i += 1) modules[size - 15 + i][8] = bitAt(i);

  modules[size - 8][8] = true; // 固定暗模块
}

/** 版本信息：6 位版本号 + BCH(18,6)。仅版本 7 及以上需要。 */
function placeVersion(modules: boolean[][], version: number): void {
  if (version < 7) return;
  const size = modules.length;
  let value = version << 12;
  for (let i = 5; i >= 0; i -= 1) {
    if ((value >>> (i + 12)) & 1) value ^= 0x1f25 << i;
  }
  const bits = (version << 12) | value;
  for (let i = 0; i < 18; i += 1) {
    const bit = ((bits >>> i) & 1) === 1;
    const row = Math.floor(i / 3);
    const column = size - 11 + (i % 3);
    modules[row][column] = bit;
    modules[column][row] = bit;
  }
}

// ---------------------------------------------------------------------------
// 对外接口
// ---------------------------------------------------------------------------

/**
 * 把文本编码成 QR 模块矩阵（`true` = 深色）。
 *
 * @param forcedMask 仅供验证使用：强制使用指定掩码而不做择优。
 *                   生产路径永远不传它——掩码择优直接影响识别率。
 * @throws 载荷超过版本 10 容量时抛错。
 */
export function encodeQrMatrix(text: string, forcedMask?: number): boolean[][] {
  if (!text) throw new Error("QR_PAYLOAD_EMPTY");
  const bytes = Array.from(new TextEncoder().encode(text));
  const version = chooseVersion(bytes.length);

  const matrix = emptyMatrix(version);
  placeFinder(matrix, 0, 0);
  placeFinder(matrix, 0, matrix.size - 7);
  placeFinder(matrix, matrix.size - 7, 0);
  placeAlignment(matrix, version);
  placeTiming(matrix);
  reserveFormatArea(matrix);
  reserveVersionArea(matrix, version);
  placeData(matrix, interleave(encodePayload(bytes, version), version));

  let best: boolean[][] | null = null;
  let bestScore = Number.POSITIVE_INFINITY;
  let bestMask = 0;
  const firstMask = forcedMask ?? 0;
  const lastMask = forcedMask ?? 7;
  for (let mask = firstMask; mask <= lastMask; mask += 1) {
    const candidate = applyMask(matrix, mask);
    placeFormat(candidate, mask);
    placeVersion(candidate, version);
    const score = penalty(candidate);
    if (score < bestScore) {
      bestScore = score;
      best = candidate;
      bestMask = mask;
    }
  }
  void bestMask;
  if (!best) throw new Error("QR_ENCODE_FAILED");
  return best;
}

/**
 * 渲染成自包含的 SVG 字符串。
 *
 * <p>用 SVG 而不是 canvas：不需要 ref、不需要等待挂载、能直接放进 JSX，
 * 且在任何缩放下都清晰——二维码扫不出来最常见的原因就是渲染尺寸太小或被拉伸。
 *
 * @param quietZone 静区模块数。规范要求至少 4，小于 4 会显著降低识别率。
 */
export function renderQrSvg(text: string, quietZone = 4): string {
  if (quietZone < 4) throw new Error("QR_QUIET_ZONE_TOO_SMALL");
  const modules = encodeQrMatrix(text);
  const size = modules.length + quietZone * 2;

  const path: string[] = [];
  modules.forEach((row, r) => {
    row.forEach((dark, c) => {
      if (dark) path.push(`M${c + quietZone} ${r + quietZone}h1v1h-1z`);
    });
  });

  return [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}"`,
    ` shape-rendering="crispEdges" role="img" aria-label="微信支付二维码">`,
    `<rect width="${size}" height="${size}" fill="#ffffff"/>`,
    `<path d="${path.join("")}" fill="#000000"/>`,
    `</svg>`,
  ].join("");
}
