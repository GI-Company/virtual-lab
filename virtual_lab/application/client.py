"""Shared in-process command adapter for desktop/web integration development.

This is not a public HTTP endpoint or an authentication system. A real web/MCP
transport must inject authenticated account/project authorization before dispatch.
"""
from __future__ import annotations
import base64
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field
from virtual_lab.application.contracts import ExperimentRef


class ResearchCommand(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)
    format: Literal['virtuallab-command-v1'] = 'virtuallab-command-v1'
    instance_id: str
    operation: Literal['instance.info','projects.list','project.create','experiments.list',
        'experiment.create','experiment.get','plan.save','conclusion.save','observations.list',
        'result.get','changes.list','simulation.submit','job.get','job.cancel','simulation.compare',
        'spectrum.import','spectrum.get']
    reference: ExperimentRef | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ResearchClient:
    def __init__(self, engine, *, surface):
        if surface not in ('desktop','web','chatgpt'):
            raise ValueError('Unknown client surface')
        self.engine, self.surface = engine, surface

    def request(self, value):
        command = ResearchCommand.model_validate(value)
        self.engine._check()
        if command.instance_id != self.engine.instance_id:
            raise ValueError('Command belongs to a different research instance')
        data = dict(command.payload)
        operation = command.operation
        reference = command.reference
        handlers = {
            'projects.list':self.engine.projects,
            'project.create':self.engine.create_project,
            'experiments.list':self.engine.experiments,
            'experiment.create':self.engine.create_experiment,
            'changes.list':self.engine.changes,
        }
        scoped = {
            'experiment.get':self.engine.experiment,
            'plan.save':self.engine.save_plan,
            'conclusion.save':self.engine.save_conclusion,
            'observations.list':self.engine.observations,
            'result.get':self.engine.result,
            'simulation.submit':self.engine.submit_simulation,
            'job.get':self.engine.job,
            'job.cancel':self.engine.cancel_job,
            'simulation.compare':self.engine.compare,
            'spectrum.get':self.engine.spectrum,
        }
        if operation == 'instance.info':
            if data:
                raise ValueError('instance.info takes no payload')
            result = {'instance_id':self.engine.instance_id,'api_version':1,
                      'scope':'Trusted local development instance; hosted authentication is not implemented',
                      'implemented_operations':list(ResearchCommand.model_fields['operation'].annotation.__args__)}
        elif operation in handlers:
            result = handlers[operation](**data)
        else:
            if reference is None:
                raise ValueError('An explicit experiment reference is required')
            if operation == 'spectrum.import':
                encoded=data.pop('source_base64')
                if not isinstance(encoded,str) or len(encoded)>24*1024*1024:
                    raise ValueError('CSV upload is too large')
                source=base64.b64decode(encoded,validate=True)
                result=self.engine.import_spectrum(reference,source,**data)
            else:
                result=scoped[operation](reference,**data)
        if isinstance(result,BaseModel):
            result=result.model_dump()
        return {'format':'virtuallab-research-response-v1','instance_id':self.engine.instance_id,
                'surface':self.surface,'operation':operation,'data':result}
