/** Local FS queue optimization only; terminal scans always bypass this schedule. */
export class LocalStorageScanSchedule {
  #dirty=true;
  #lastScan=0;
  changed(filename:string|null):void {
    // Bounded host log snapshots do not dirty the entire generated workspace.
    // Missing/ambiguous names and all actual output paths remain dirty.
    if(filename!=="job.json" && !/^job\.json\.[0-9a-f-]{36}\.tmp$/.test(filename??""))this.#dirty=true;
  }
  due(watcherAvailable:boolean,now:number):boolean {
    return !watcherAvailable || this.#dirty || now-this.#lastScan>=30_000;
  }
  started(now:number):void {this.#dirty=false;this.#lastScan=now;}
}
