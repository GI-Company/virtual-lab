# VirtualLab — full application plugin preparation

**Target:** the whole VirtualLab application discoverable through ChatGPT's public Plugins directory. This is not a proposal to publish the minimal BSA snapshot adapter as the VirtualLab product.

**Status:** full-scope submission preparation. Not submitted, approved, published or searchable. The full application has not been ported to ChatGPT yet. The local MS MCP proof of concept remains a separate engineering test fixture.

Publisher contact supplied by the owner: **cory.tortorici@globalintentcompany.space**. The publisher name is Global Intent Company; OpenAI business/individual verification has not been observed. No email has been sent.

## Prepared materials

- `plugin.json`: portable full-scope plugin identity and draft directory metadata.
- `mcp.json`: proposed public HTTPS connection shape. Its endpoint is not deployed or verified.
- `assets/virtuallab.svg`: original, provisional square flask/spectrum mark. No desktop screenshot is misrepresented as a ChatGPT interface.
- `capability-parity.json`: all 15 installed tool workspaces plus Settings, their existing services, required plugin behavior and acceptance checks.
- `release-profile.json`: supplied contact, proposed domains and explicit uncompleted release gates.
- `review/test-plan.json`: five positive and three negative full-application review designs. They have not been run in ChatGPT.
- `policies/`: factual privacy and terms preparation worksheets, not approved legal policies.
- `FULL-APPLICATION-PLAN.md`: implementation stages, shared-engine design and publication acceptance.

Build a visibly marked draft package with:

```bash
python scripts/prepare_plugin_submission.py
```

The builder checks documented package fields, paths, image dimensions and listing limits. It is not OpenAI's package validator. It creates a **DRAFT** ZIP and readiness report; it does not create a publicly usable service or submit anything. `--require-ready` fails while any full-application or publication gate remains open.

## Public URLs are proposed, not claimed live

The existing product page was verified in the browser at `/virtual-lab`; the remaining addresses below are proposed paths recorded in the release profile:

- Existing product page: `https://globalintentcompany.space/virtual-lab`
- Support: `https://globalintentcompany.space/virtuallab/support`
- Privacy: `https://globalintentcompany.space/virtuallab/privacy`
- Terms: `https://globalintentcompany.space/virtuallab/terms`
- MCP: `https://api.globalintentcompany.space/mcp`

The existing product page and paid online-demo entry are reachable in the browser. The proposed support/policy/MCP addresses, domain control and deployment configuration have not been verified. An email address alone does not establish ownership of a website or a public MCP service. Replace these addresses if the owner selects different paths. Do not upload this draft claiming they work.

## What makes it searchable

OpenAI's current submission flow requires a package and functioning public integration, required public information, verified publisher identity, review and approval, followed by the publisher's Publish action. A local MCP entry, private connection or repository marketplace does not make a plugin appear in the universal public directory. Search visibility follows publication, and approval does not guarantee featured placement.

A full-application listing must wait until the actual full application works through the plugin. Do not advertise unavailable tools as implemented merely because their names are present in a manifest or roadmap.

Official sources checked for this preparation:

- [Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [Upload, review and publish](https://developers.openai.com/plugins/deploy/submission)
- [Remote MCP review and discovery requirements](https://developers.openai.com/plugins/deploy/app-review)
- [Interactive UI in ChatGPT](https://developers.openai.com/plugins/build/chatgpt-ui)

## Things this packet does not do

It does not redistribute the native application, grant a software/data license, deploy a website, provision hosting, create an OpenAI organization, verify the publisher, submit a review, transmit laboratory data, or publish a directory entry. The repository's licensing decision remains with its owner. The full existing desktop application remains intact.

## Selected shared experience

The owner selected both the full interactive ChatGPT workspace and paired desktop, sharing the same projects and research engine. The developing website is the browser fallback. [The first shared-engine implementation](../../docs/shared-research-engine.md) is complete locally; the live website/ChatGPT/desktop transport and full feature parity remain open.
