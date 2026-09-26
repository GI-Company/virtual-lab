"""
virtual_lab.gateway.mcp_adapter
───────────────────────────────
Model Context Protocol (MCP) adapter for the Virtual Lab Gateway.
Exposes Virtual Lab read-only discovery tools to Vertex AI and other agent frameworks.
Translates between MCP protocol formats and the vlab.tool.v1 internal contract.
"""

import json
from typing import Dict, Any, List, Optional
from virtual_lab.gateway.engine import GatewayEngine


class MCPAdapter:
    def __init__(self, engine: Optional[GatewayEngine] = None):
        self.engine = engine if engine is not None else GatewayEngine()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Returns Model Context Protocol (MCP) tool declarations.
        """
        return [
            {
                "name": "device_list",
                "description": "Discover all hardware instruments and SensorNode devices currently connected or known to Virtual Lab. Returns an empty list if no hardware is attached.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "device_describe",
                "description": "Retrieve factual specifications and capabilities of a known Virtual Lab hardware device. Never returns fabricated properties.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Unique device identifier (e.g. sensornode-01, sensornode-adb-<serial>)."
                        }
                    },
                    "required": ["device_id"]
                }
            },
            {
                "name": "device_status",
                "description": "Query live connectivity and diagnostic status for a hardware device (ONLINE, OFFLINE, DEGRADED, BUSY).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Unique device identifier to check."
                        }
                    },
                    "required": ["device_id"]
                }
            },
            {
                "name": "device_calibration_get",
                "description": "Retrieve verified calibration metadata for a device. Returns UNAVAILABLE if no calibration record exists.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Unique device identifier."
                        }
                    },
                    "required": ["device_id"]
                }
            }
        ]

    def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        requesting_agent: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes an MCP tool call by mapping it to the underlying GatewayEngine.
        Returns standard MCP-compatible tool call response:
        {"content": [{"type": "text", "text": "<json-string>"}], "isError": bool}
        """
        name_mapping = {
            "device_list": "device.list",
            "device_describe": "device.describe",
            "device_status": "device.status",
            "device_calibration_get": "device.calibration.get"
        }

        gateway_tool = name_mapping.get(name)
        if not gateway_tool:
            err_payload = {
                "schema_version": "vlab.tool.v1",
                "tool": name,
                "state": "FAILED",
                "errors": [{"code": "UNKNOWN_MCP_TOOL", "message": f"Tool '{name}' is not recognized by Virtual Lab Gateway."}]
            }
            return {
                "content": [{"type": "text", "text": json.dumps(err_payload, indent=2)}],
                "isError": True
            }

        response = self.engine.execute_tool(
            tool_name=gateway_tool,
            arguments=arguments or {},
            correlation_id=correlation_id,
            requesting_agent=requesting_agent
        )

        resp_dict = response.model_dump()
        is_error = response.state.value in ("FAILED", "REJECTED")

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(resp_dict, indent=2)
                }
            ],
            "isError": is_error
        }
