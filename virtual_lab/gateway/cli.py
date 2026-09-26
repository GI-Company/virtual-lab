"""
virtual_lab.gateway.cli
───────────────────────
Command-line interface for testing and interacting with the Virtual Lab Gateway.
"""

import sys
import json
import argparse
from virtual_lab.gateway.api import (
    device_list,
    device_describe,
    device_status,
    device_calibration_get,
)


def main():
    parser = argparse.ArgumentParser(
        prog="virtual-lab-gateway",
        description="Virtual Lab Tool Gateway - Phase 1 Read-Only Device Discovery"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available gateway commands")

    # device.list
    subparsers.add_parser("list", help="List all discovered physical instruments and SensorNodes")

    # device.describe
    desc_parser = subparsers.add_parser("describe", help="Describe hardware characteristics of a device")
    desc_parser.add_argument("device_id", help="Target device ID")

    # device.status
    stat_parser = subparsers.add_parser("status", help="Query live status and diagnostics for a device")
    stat_parser.add_argument("device_id", help="Target device ID")

    # device.calibration.get
    cal_parser = subparsers.add_parser("calibration", help="Get calibration metadata for a device")
    cal_parser.add_argument("device_id", help="Target device ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "list":
        resp = device_list(requesting_agent="cli_operator")
    elif args.command == "describe":
        resp = device_describe(args.device_id, requesting_agent="cli_operator")
    elif args.command == "status":
        resp = device_status(args.device_id, requesting_agent="cli_operator")
    elif args.command == "calibration":
        resp = device_calibration_get(args.device_id, requesting_agent="cli_operator")
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(resp.model_dump(), indent=2))
    if resp.state.value in ("FAILED", "REJECTED"):
        sys.exit(1)


if __name__ == "__main__":
    main()
