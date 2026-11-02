"""Freeze/check server-owned policy and shared report JSON schemas."""
import argparse
import json
from pathlib import Path

from virtual_lab.integrations.research_service.contracts import SharedMSReport
from virtual_lab.integrations.research_service.policy import AccessPolicy
from virtual_lab.integrations.research_service.campaign_requests import CreateCampaign, StartCampaign, CampaignCommand

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT/'integrations/shared-engine-contract'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    for name,model in [('service-access-policy',AccessPolicy),('service-ms-report',SharedMSReport),
                       ('service-campaign-create',CreateCampaign), ('service-campaign-start',StartCampaign),
                       ('service-campaign-command',CampaignCommand)]:
        raw = (json.dumps(model.model_json_schema(),indent=2,sort_keys=True)+'\n').encode()
        path = DIRECTORY/(name+'.schema.json')
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit('Schema differs: '+name)
        else:
            path.write_bytes(raw)
    print('Research service contract schemas match source.' if args.check else 'Exported research service contract schemas.')


if __name__ == '__main__':
    main()
