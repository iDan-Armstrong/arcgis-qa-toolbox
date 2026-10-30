"""Publish the Feature Class QA tool as a geoprocessing service on ArcGIS Enterprise.

Run inside an ArcGIS Pro / Server Python environment:

    python gp_service/publish_gp_service.py ^
        --portal https://portal.example.com/portal ^
        --server https://server.example.com/server ^
        --fc "C:/data/staging.gdb/facilities" ^
        --rules examples/facility_rules.json

Flow (the standard three-step Esri publish, scripted so it is repeatable):
  1. run the tool once locally       -> arcpy needs a successful run to package
  2. CreateGPSDDraft + staging       -> .sddraft -> .sd (fails loudly on analyzer errors)
  3. UploadServiceDefinition         -> live service

Credentials come from the environment (PORTAL_USER / PORTAL_PASSWORD) or an
active Pro sign-in — never from arguments, never hardcoded.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import arcpy

REPO = Path(__file__).resolve().parents[1]
PYT = REPO / "toolbox" / "QAToolbox.pyt"


def run_once(fc: str, rules: str):
    """arcpy requires a successful local run of the tool to create a draft from."""
    arcpy.ImportToolbox(str(PYT))
    result = arcpy.qatoolbox.FeatureClassQA(fc, rules, False)  # type: ignore[attr-defined]
    arcpy.AddMessage("local run complete")
    return result


def publish(result, server: str, service_name: str, folder: str | None) -> str:
    tmp = Path(tempfile.mkdtemp())
    sddraft = str(tmp / f"{service_name}.sddraft")
    sd = str(tmp / f"{service_name}.sd")

    # CreateGPSDDraft runs the service analyzers and returns their findings
    analysis = arcpy.CreateGPSDDraft(
        result,
        sddraft,
        service_name,
        server_type="MY_HOSTED_SERVICES",
        copy_data_to_server=False,
        folder_name=folder,
        summary="Declarative QA rules over a feature class (qacore engine)",
        tags="QA, data quality, geoprocessing",
        executionType="Asynchronous",
        resultMapServer=False,
        maxRecords=10000,
        minInstances=0,
        maxInstances=2,
    )
    for (message, _code), layers in analysis.get("warnings", {}).items():
        arcpy.AddWarning(f"analyzer: {message} ({layers})")
    if analysis.get("errors"):
        for (message, _code), layers in analysis["errors"].items():
            arcpy.AddError(f"analyzer: {message} ({layers})")
        raise SystemExit("sddraft analysis failed — fix errors above before publishing")

    arcpy.server.StageService(sddraft, sd)
    item = arcpy.server.UploadServiceDefinition(sd, server)
    arcpy.AddMessage(f"published: {service_name}")
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portal", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--fc", required=True, help="feature class for the definition run")
    parser.add_argument("--rules", required=True, help="rules JSON for the definition run")
    parser.add_argument("--name", default="FeatureClassQA")
    parser.add_argument("--folder", default=None)
    args = parser.parse_args()

    user, password = os.environ.get("PORTAL_USER"), os.environ.get("PORTAL_PASSWORD")
    if user and password:
        arcpy.SignInToPortal(args.portal, user, password)
    # else: rely on the active Pro sign-in

    result = run_once(args.fc, args.rules)
    publish(result, args.server, args.name, args.folder)


if __name__ == "__main__":
    main()
