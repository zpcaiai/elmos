const assert = require('assert');
const fs = require('fs');
const path = require('path');

let totalTests = 0;
let passedTests = 0;
let failedTests = 0;
let currentSuite = '';

function expect(actual) {
  return {
    toBe(expected) {
      assert.strictEqual(actual, expected);
    },
    toEqual(expected) {
      assert.deepStrictEqual(actual, expected);
    },
    toBeGreaterThan(expected) {
      assert.ok(actual > expected, `Expected ${actual} to be > ${expected}`);
    },
    toBeGreaterThanOrEqual(expected) {
      assert.ok(actual >= expected, `Expected ${actual} to be >= ${expected}`);
    },
    toBeLessThan(expected) {
      assert.ok(actual < expected, `Expected ${actual} to be < ${expected}`);
    },
    toBeDefined() {
      assert.notStrictEqual(actual, undefined);
    },
    toBeUndefined() {
      assert.strictEqual(actual, undefined);
    },
    toBeNull() {
      assert.strictEqual(actual, null);
    },
    toBeTruthy() {
      assert.ok(actual);
    },
    toBeFalsy() {
      assert.ok(!actual);
    },
    toContain(item) {
      if (typeof actual === 'string') {
        assert.ok(actual.includes(item), `Expected "${actual}" to contain "${item}"`);
      } else if (Array.isArray(actual)) {
        assert.ok(actual.includes(item), `Expected array to contain ${item}`);
      } else {
        throw new Error('Unsupported toContain type');
      }
    },
    toHaveLength(len) {
      assert.strictEqual(actual.length, len);
    },
    toThrow(expectedMsg) {
      assert.throws(() => {
        if (typeof actual === 'function') actual();
      }, expectedMsg ? new RegExp(expectedMsg) : undefined);
    },
    async rejects() {
      return {
        toThrow(expectedMsg) {
          return assert.rejects(actual, expectedMsg ? new RegExp(expectedMsg) : undefined);
        }
      };
    }
  };
}

global.expect = expect;

let beforeEachHooks = [];

global.describe = function(name, fn) {
  const prevSuite = currentSuite;
  currentSuite = prevSuite ? `${prevSuite} > ${name}` : name;
  const prevHooks = [...beforeEachHooks];
  try {
    fn();
  } finally {
    currentSuite = prevSuite;
    beforeEachHooks = prevHooks;
  }
};

global.beforeEach = function(hook) {
  beforeEachHooks.push(hook);
};

const testQueue = [];

global.it = function(name, fn) {
  const suite = currentSuite;
  const hooks = [...beforeEachHooks];
  testQueue.push({ suite, name, fn, hooks });
};

async function run() {
  const testDir = path.join(__dirname, 'dist', 'test');
  const files = fs.readdirSync(testDir).filter(f => f.endsWith('.spec.js'));

  console.log(`[TypeScript Test Runner] Loading ${files.length} test suites...`);
  for (const file of files) {
    require(path.join(testDir, file));
  }

  console.log(`[TypeScript Test Runner] Executing ${testQueue.length} test cases...`);
  for (const t of testQueue) {
    totalTests++;
    try {
      for (const h of t.hooks) {
        await h();
      }
      await t.fn();
      passedTests++;
      console.log(`  ✓ ${t.suite} -> ${t.name}`);
    } catch (err) {
      failedTests++;
      console.error(`  ✗ ${t.suite} -> ${t.name}`);
      console.error(`    ${err.stack || err}`);
    }
  }

  console.log(`\n========================================`);
  console.log(`Results: ${passedTests} passed, ${failedTests} failed, ${totalTests} total`);
  console.log(`========================================`);

  if (failedTests > 0) {
    process.exit(1);
  }
}

run().catch(err => {
  console.error(err);
  process.exit(1);
});
