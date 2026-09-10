// Top-level helpers and constants
try { const paths = {
    home: d, "M3 11.5 12 4l9 7.5": /><path d="M5.5 10v10h13V10M9 20v-6h6v6"/ > />,,
    route: cx, "6": cy = "6", r = "2.5" /  > cx, "18": cy = "18", r = "2.5" /  > d, "M8.5 6h3.8A3.7 3.7 0 0 1 16 9.7v4.6M13 11l3 3 3-3": /></ > ,
    shield: d, "M12 3 20 6v5c0 5.2-3.3 8.4-8 10-4.7-1.6-8-4.8-8-10V6l8-3Z": /><path d="m8.5 12 2.2 2.2 4.8-5"/ > />,,
    box: d, "m4 7 8-4 8 4-8 4-8-4Z": /><path d="m4 7v10l8 4 8-4V7M12 11v10"/ > />,,
    settings: cx, "12": cy = "12", r = "3" /  > d, "M19 13.5v-3l-2-.7a7 7 0 0 0-.7-1.7l.9-1.9-2.1-2.1-1.9.9a7 7 0 0 0-1.7-.7L10.5 2h-3l-.7 2a7 7 0 0 0-1.7.7l-1.9-.9-2.1 2.1.9 1.9a7 7 0 0 0-.7 1.7L0 10.5v3l2 .7a7 7 0 0 0 .7 1.7l-.9 1.9 2.1 2.1 1.9-.9a7 7 0 0 0 1.7.7l.7 2h3l.7-2a7 7 0 0 0 1.7-.7l1.9.9 2.1-2.1-.9-1.9a7 7 0 0 0 .7-1.7l2-.7Z": transform = "translate(2 -0.5) scale(.83)" /  > />,,
    help: cx, "12": cy = "12", r = "9" /  > d, "M9.8 9a2.3 2.3 0 1 1 3.7 1.8c-1 .7-1.5 1.1-1.5 2.2M12 17h.01": /></ > ,
    arrow: d, "M5 12h14M14 7l5 5-5 5": /></ > ,
    check: d, "m5 12 4 4L19 6": />,,
    clock: cx, "12": cy = "12", r = "9" /  > d, "M12 7v5l3 2": /></ > ,
    lock: x, "5": y = "10", width = "14", height = "10", rx = "2" /  > d, "M8 10V7a4 4 0 0 1 8 0v3": /></ > ,
    search: cx, "10.5": cy = "10.5", r = "6.5" /  > d, "m16 16 4 4": /></ > ,
    plus: d, "M12 5v14M5 12h14": />,,
    filter: d, "M4 6h16M7 12h10M10 18h4": />,,
    code: d, "m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16": />,,
    database: cx, "12": cy = "5.5", rx = "8", ry = "3" /  > d, "M4 5.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6M4 11.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6": /></ > ,
    cloud: d, "M7 18h10a4 4 0 0 0 .5-8 6 6 0 0 0-11.4-1.4A4.8 4.8 0 0 0 7 18Z": />,,
    layers: d, "m12 3 9 5-9 5-9-5 9-5Z": /><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/ > />,,
    workflow: x, "3": y = "4", width = "6", height = "5", rx = "1" /  > x, "15": y = "15", width = "6", height = "5", rx = "1" /  > d, "M9 6.5h4a4 4 0 0 1 4 4V15M14 12l3 3 3-3": /></ > ,
    spark: d, "m12 2 1.5 5.5L19 9l-5.5 1.5L12 16l-1.5-5.5L5 9l5.5-1.5L12 2Z": /><path d="m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15Z"/ > />,,
    menu: d, "M4 7h16M4 12h16M4 17h16": />,,
    close: d, "m6 6 12 12M18 6 6 18": />,,
    refresh: d, "M20 7v5h-5M4 17v-5h5": /><path d="M18.2 9A7 7 0 0 0 6.5 6.5L4 9M5.8 15A7 7 0 0 0 17.5 17.5L20 15"/ > />,,
    repository: d, "M5 4h11a3 3 0 0 1 3 3v13H7a2 2 0 0 1-2-2V4Z": /><path d="M5 16h12M9 8h6"/ > />,,
    server: x, "3": y = "4", width = "18", height = "6", rx = "2" /  > x, "3": y = "14", width = "18", height = "6", rx = "2" /  > d, "M7 7h.01M7 17h.01M11 7h6M11 17h6": /></ > ,
    file: d, "M6 3h8l4 4v14H6V3Z": /><path d="M14 3v5h5M9 13h6M9 17h5"/ > />,,
    user: cx, "12": cy = "8", r = "4" /  > d, "M4.5 21a7.5 7.5 0 0 1 15 0": /></ > ,
    chevron: d, "m9 6 6 6-6 6": />,,
    external: d, "M14 4h6v6M20 4l-9 9": /><path d="M18 13v7H4V6h7"/ > />,,
    command: d, "M9 6V4a2 2 0 1 0-2 2h10a2 2 0 1 0-2-2v16a2 2 0 1 0 2-2H7a2 2 0 1 0 2 2V6Z": /></ > ,
    test: d, "M9 3h6M10 3v5l-5 9a2.5 2.5 0 0 0 2.2 4h9.6a2.5 2.5 0 0 0 2.2-4l-5-9V3": /><path d="M8 15h8M9.5 18h5"/ > />,,
    copy: x, "8": y = "8", width = "11", height = "11", rx = "2" /  > d, "M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3": /></ > ,
    play: d, "m8 5 11 7-11 7V5Z": />,
}; } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    name: {
      type: null,
      value: null,
    },
    size: {
      type: null,
      value: 20,
    },
    className: {
      type: null,
      value: null,
    },
  },
  data: {
  },
  lifetimes: {
    attached() {
    },
    detached() {
    },
  },
  methods: {
  },
});
