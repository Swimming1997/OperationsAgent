def test_domain_facades_import_without_side_effects():
    from intelligence_engine.accounts.services import AccountLoginService
    from intelligence_engine.content.services import ContentRepository
    from intelligence_engine.jobs.diagnostics import collect_job_queue_report
    from intelligence_engine.jobs.maintenance import JobMaintenanceService
    from intelligence_engine.jobs.queue import JobRepository
    from intelligence_engine.operations.services import JobOperationsService
    from intelligence_engine.organization.repositories import ProductRepository
    from intelligence_engine.reference_library.services import BenchmarkSelectionService
    from intelligence_engine.rules.services import OperationRuleRepository

    assert AccountLoginService
    assert ContentRepository
    assert collect_job_queue_report
    assert JobMaintenanceService
    assert JobRepository
    assert JobOperationsService
    assert ProductRepository
    assert BenchmarkSelectionService
    assert OperationRuleRepository

