
import { parseTemplate } from "@angular/compiler";
const template = JSON.parse(process.argv[2]);
const result = parseTemplate(template, "emitted.component.html");
process.stdout.write(JSON.stringify((result.errors ?? []).map(String)));
