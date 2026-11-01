import time
import pytest

from virtual_lab.application.engine import ResearchEngine
from virtual_lab.application.campaigns import ResearchCampaigns


@pytest.fixture
def owned(tmp_path):
    engine = ResearchEngine(tmp_path / 'campaign-instance')
    project = engine.create_project('Custom research')
    reference = engine.create_experiment(project['id'], 'User conditions', 'Compare two assumed exposures')
    yield engine, reference
    engine.close()


def create(controller, ref, **changes):
    fields = dict(objective='Compare my two custom assumed conditions',
                  configs=[dict(model_id='gene_expression', concentration_um=v, members=2, duration_h=1)
                           for v in (2, 7)], max_runs=2, max_seconds=60)
    fields.update(changes)
    return controller.create(ref, **fields)


def finish(controller, ref, identity, *, steps=None):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        result = controller.advance(ref, identity)
        if result['state'] not in ('RUNNING', 'CANCELLING') or (steps and result['next_step'] == steps):
            return result
        time.sleep(.01)
    raise AssertionError('Campaign did not settle')


def test_real_custom_runs_resume_after_restart_without_duplicates(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    plan = create(controller, ref)
    controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
    first = finish(controller, ref, plan['id'], steps=1)
    controller.pause(ref, plan['id'])
    engine.close()
    reopened = ResearchEngine(engine.root)
    try:
        resumed = ResearchCampaigns(reopened)
        assert resumed.get(ref, plan['id'])['observations'] == first['observations']
        assert resumed.advance(ref, plan['id'])['state'] == 'PAUSED'
        resumed.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
        done = finish(resumed, ref, plan['id'])
        assert done['state'] == 'COMPLETED' and done['next_step'] == 2
        assert len(reopened.observations(ref)) == 2
        assert resumed.advance(ref, plan['id']) == done
        assert all(row['epistemic_state'] == 'SIMULATED' for row in reopened.observations(ref))
        assert any(row['delta'] != 0 for row in reopened.compare(ref, *done['observations']))
        operations = [c['operation'] for c in reopened.changes(ref.project_id)['changes']]
        assert 'campaign_checkpointed' in operations and 'campaign_started' in operations
    finally:
        reopened.close()


def test_plan_approval_and_cross_project_scope(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    plan = create(controller, ref)
    with pytest.raises(ValueError, match='Approval'):
        controller.start(ref, plan['id'], approved_plan_sha256='unapproved')
    other = engine.create_project('Other')
    other_ref = engine.create_experiment(other['id'], 'Other experiment', 'Unrelated')
    with pytest.raises(ValueError, match='does not belong'):
        controller.get(other_ref, plan['id'])
    assert controller.advance(ref, plan['id'])['state'] == 'DRAFT'
    assert engine.observations(ref) == []


@pytest.mark.parametrize('changes', [dict(max_runs=True), dict(max_runs=1), dict(max_seconds=False),
                                    dict(configs=[]), dict(max_runs=21), dict(max_seconds=86401)])
def test_plan_must_fit_finite_budgets(owned, changes):
    engine, ref = owned
    with pytest.raises(ValueError):
        create(ResearchCampaigns(engine), ref, **changes)


def test_deadline_stops_before_launch_and_cannot_be_reset(owned):
    engine, ref = owned
    clock = [100]
    controller = ResearchCampaigns(engine, clock=lambda: clock[0])
    plan = create(controller, ref, max_seconds=1)
    controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
    controller.pause(ref, plan['id'])
    clock[0] = 102
    controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
    result = controller.advance(ref, plan['id'])
    assert result['state'] == 'NEEDS_REVIEW' and result['error_code'] == 'WALL_CLOCK_BUDGET'
    assert engine.observations(ref) == []
    with pytest.raises(ValueError):
        controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])


def test_cancel_draft_executes_nothing(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    plan = create(controller, ref)
    assert controller.cancel(ref, plan['id'])['state'] == 'CANCELLED'
    assert controller.advance(ref, plan['id'])['state'] == 'CANCELLED'
    assert engine.observations(ref) == []


def test_modified_saved_plan_fails_before_execution(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    plan = create(controller, ref)
    with engine.store._conn:
        engine.store._conn.execute('UPDATE research_campaigns SET plan=? WHERE id=?', ('{}', plan['id']))
    with pytest.raises(ValueError, match='integrity'):
        controller.advance(ref, plan['id'])
    assert engine.observations(ref) == []


def test_running_cancellation_releases_engine_capacity(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    plan = create(controller, ref)
    controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
    controller.advance(ref, plan['id'])
    controller.cancel(ref, plan['id'])
    assert finish(controller, ref, plan['id'])['state'] == 'CANCELLED'
    assert not engine.settings.busy
    assert engine.observations(ref) == []


def test_lost_submission_checkpoint_reuses_job_and_requires_review_after_restart(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    plan = create(controller, ref)
    controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
    # Simulate a crash after engine submission but before saving the campaign job ID.
    engine.submit_simulation(ref, plan['plan']['configs'][0], request_id=f"campaign:{plan['id']}:0")
    engine.close()
    reopened = ResearchEngine(engine.root)
    try:
        resumed = ResearchCampaigns(reopened)
        resumed.advance(ref, plan['id'])
        result = resumed.advance(ref, plan['id'])
        assert result['state'] == 'NEEDS_REVIEW'
        count = reopened.store._conn.execute('SELECT COUNT(*) FROM application_jobs').fetchone()[0]
        assert count == 1 and reopened.observations(ref) == []
    finally:
        reopened.close()


@pytest.mark.parametrize('stop', ['cancel', 'deadline', 'revoked'])
def test_stop_recovers_and_reaps_job_after_lost_submission_checkpoint(owned, stop):
    engine, ref = owned
    clock = [100]
    controller = ResearchCampaigns(engine, clock=lambda: clock[0])
    plan = create(controller, ref, max_seconds=5)
    controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
    submitted = engine.submit_simulation(
        ref, plan['plan']['configs'][0], request_id=f"campaign:{plan['id']}:0")
    assert controller.get(ref, plan['id'])['active_job_id'] is None
    if stop == 'cancel':
        stopped = controller.cancel(ref, plan['id'])
    elif stop == 'deadline':
        clock[0] = 106
        stopped = controller.advance(ref, plan['id'])
    else:
        stopped = controller.stop_for_review(ref, plan['id'], 'ACCESS_REVOKED')
    assert stopped['active_job_id'] == submitted.id
    result = finish(controller, ref, plan['id'])
    assert result['state'] == ('CANCELLED' if stop == 'cancel' else 'NEEDS_REVIEW')
    assert result['active_job_id'] is None
    assert result['error_code'] == {'cancel': None, 'deadline': 'WALL_CLOCK_BUDGET',
                                    'revoked': 'ACCESS_REVOKED'}[stop]
    assert not engine.settings.busy and not engine._processes
    assert engine.observations(ref) == []
    assert engine.store._conn.execute('SELECT COUNT(*) FROM application_jobs').fetchone()[0] == 1


def test_paused_recovery_and_reads_never_launch_another_job(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    plan = create(controller, ref)
    controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
    submitted = engine.submit_simulation(
        ref, plan['plan']['configs'][0], request_id=f"campaign:{plan['id']}:0")
    controller.pause(ref, plan['id'])
    engine._processes[submitted.id]['process'].wait(timeout=20)
    # Inspecting a campaign neither accepts the completed worker output nor
    # repairs its missing checkpoint. That requires an owner tick.
    assert controller.get(ref, plan['id'])['active_job_id'] is None
    assert engine.observations(ref) == []
    recovered = controller.advance(ref, plan['id'])
    assert recovered['state'] == 'PAUSED' and recovered['next_step'] == 1
    assert len(recovered['observations']) == 1 and not engine.settings.busy
    assert controller.advance(ref, plan['id']) == recovered
    assert engine.store._conn.execute('SELECT COUNT(*) FROM application_jobs').fetchone()[0] == 1


def test_shared_capacity_queues_second_campaign_without_failing_it(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    first = create(controller, ref)
    second = create(controller, ref)
    for plan in (first, second):
        controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
    controller.advance(ref, first['id'])
    queued = controller.advance(ref, second['id'])
    assert queued['state'] == 'RUNNING' and queued['active_job_id'] is None
    assert engine.store._conn.execute('SELECT COUNT(*) FROM application_jobs').fetchone()[0] == 1
    assert finish(controller, ref, first['id'])['state'] == 'COMPLETED'
    assert finish(controller, ref, second['id'])['state'] == 'COMPLETED'
    assert len(engine.observations(ref)) == 4


def test_campaign_creation_idempotency_is_exact_and_scoped(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    original = create(controller, ref, request_id='accepted-request')
    controller.start(ref, original['id'], approved_plan_sha256=original['plan_sha256'])
    repeated = create(controller, ref, request_id='accepted-request')
    assert repeated['id'] == original['id'] and repeated['state'] == 'RUNNING'
    with pytest.raises(ValueError, match='different research plan'):
        create(controller, ref, request_id='accepted-request', objective='Different objective')
    other_ref = engine.create_experiment(ref.project_id, 'Another', 'Independent plan')
    other = create(controller, other_ref, request_id='accepted-request')
    assert other['id'] != original['id']
    assert engine.store._conn.execute('SELECT COUNT(*) FROM research_campaigns').fetchone()[0] == 2


def test_review_stop_preserves_already_committed_result_after_checkpoint_loss(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    plan = create(controller, ref)
    controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
    submitted = engine.submit_simulation(
        ref, plan['plan']['configs'][0], request_id=f"campaign:{plan['id']}:0")
    engine._processes[submitted.id]['process'].wait(timeout=20)
    completed = engine.job(ref, submitted.id)
    assert completed.state == 'COMPLETED'
    controller.stop_for_review(ref, plan['id'], 'ACCESS_REVOKED')
    result = finish(controller, ref, plan['id'])
    assert result['state'] == 'NEEDS_REVIEW'
    assert result['observations'] == [completed.result_observation_id]
    assert result['next_step'] == 1
    with pytest.raises(ValueError, match='Only draft or paused'):
        controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])


def test_recovery_rejects_different_inputs_under_campaign_request_id(owned):
    engine, ref = owned
    controller = ResearchCampaigns(engine)
    plan = create(controller, ref)
    controller.start(ref, plan['id'], approved_plan_sha256=plan['plan_sha256'])
    engine.submit_simulation(ref, plan['plan']['configs'][1], request_id=f"campaign:{plan['id']}:0")
    with pytest.raises(ValueError, match='approved step'):
        controller.advance(ref, plan['id'])
    assert controller.get(ref, plan['id'])['active_job_id'] is None
