import assert from 'node:assert/strict';
import test from 'node:test';
import { LocalStorageScanSchedule } from '../app/lib/server/localStorageScanSchedule.ts';
test('bounded host log snapshots do not cause whole-workspace polling scans',()=>{
  const schedule=new LocalStorageScanSchedule();assert.equal(schedule.due(true,0),true);schedule.started(0);
  for(let index=0;index<100_000;index++) {
    schedule.changed('job.json');schedule.changed('job.json.00000000-0000-4000-8000-000000000001.tmp');
  }
  assert.equal(schedule.due(true,29_999),false);assert.equal(schedule.due(true,30_000),true);
});
test('output, unknown watch events, and missing watcher preserve exact scanning',()=>{
  const schedule=new LocalStorageScanSchedule();schedule.started(100);
  schedule.changed('workspace/src/code.py');assert.equal(schedule.due(true,101),true);
  schedule.started(102);schedule.changed(null);assert.equal(schedule.due(true,103),true);
  schedule.started(104);assert.equal(schedule.due(false,105),true);
  schedule.changed('workspace/job.json');assert.equal(schedule.due(true,105),true);
});
