#!/usr/bin/env python3
"""Use the exact tested reactor classpath, not potentially stale installed jars."""
import argparse
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument("--heap", default="64m")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
report = root / "modules/integrations/target/surefire-reports/TEST-io.elmos.integrations.CasBackedArtifactStoreTest.xml"
classpath = next(p.attrib["value"] for p in ET.parse(report).findall("./properties/property")
                 if p.attrib["name"] == "java.class.path")
subprocess.run(["java", f"-Xmx{args.heap}", "-cp", classpath,
                "io.elmos.integrations.StreamingHeapProbe"], check=True, timeout=300)
