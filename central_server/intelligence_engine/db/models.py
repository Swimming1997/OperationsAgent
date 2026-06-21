from sqlalchemy import Index

from intelligence_engine.db.model_base import JsonType, TimestampMixin, new_uuid, utcnow
from intelligence_engine.db.account_models import (
    AccountAgentBinding,
    AccountLoginSession,
    AccountSession,
    AgentAccountSnapshot,
    LocalAgent,
    PlatformAccount,
)
from intelligence_engine.db.content_models import (
    CandidateDecision,
    CommentSnapshot,
    ContentAssignment,
    ContentDiscoveryEvent,
    ContentIdentity,
    ContentManualTag,
    ContentOperatorNote,
    ContentSnapshot,
    ContentWorkflowState,
    CreatorMonitor,
    CreatorMonitorEvent,
    ManualTag,
    UserIntelligenceScenarioFilter,
)
from intelligence_engine.db.job_models import FetchLease, Job, JobEvent, TaskRun
from intelligence_engine.db.organization_models import BusinessAccountType, Employee, Role, User, UserRole
from intelligence_engine.db.reference_library_models import (
    BenchmarkGroup,
    BenchmarkGroupMember,
    BusinessAccountTypeBenchmarkGroup,
    ReferenceLibraryEvent,
    ReferenceLibraryItem,
)
from intelligence_engine.db.rule_models import (
    BusinessAccountTypeRuleSet,
    KeywordRule,
    KeywordRuleSet,
    OperationRule,
    RuleProfile,
    XhsSearchSuggestion,
)
from intelligence_engine.db.task_models import BehaviorProfile, NetworkEgressProfile, RiskPolicy, TaskSchedule, TaskTemplate

Index("idx_jobs_status_priority", Job.status, Job.priority, Job.scheduled_at)
Index("idx_jobs_task_run_id", Job.task_run_id)
Index("idx_jobs_account_id", Job.account_id)
Index("idx_jobs_agent_id", Job.local_agent_id)
Index("idx_jobs_claim_expiry", Job.claim_expires_at)
Index("idx_jobs_job_type", Job.job_type)
Index("idx_job_events_job_id_created", JobEvent.job_id, JobEvent.created_at)
Index("idx_content_identity_last_seen", ContentIdentity.last_seen_at)
Index("idx_content_identity_platform", ContentIdentity.platform)
Index("idx_content_identity_content_type", ContentIdentity.content_type)
Index("idx_discovery_content_id", ContentDiscoveryEvent.content_id)
Index("idx_discovery_account_id", ContentDiscoveryEvent.account_id)
Index("idx_discovery_job_id", ContentDiscoveryEvent.job_id)
Index("idx_discovery_discovered_at", ContentDiscoveryEvent.discovered_at)
Index("idx_discovery_content_discovered_at", ContentDiscoveryEvent.content_id, ContentDiscoveryEvent.discovered_at)
Index("idx_discovery_surface", ContentDiscoveryEvent.source_surface)
Index("idx_reference_library_content_status", ReferenceLibraryItem.content_id, ReferenceLibraryItem.status)
Index("idx_content_snapshots_content_id", ContentSnapshot.content_id, ContentSnapshot.fetched_at.desc())
Index("idx_content_snapshots_publish_time", ContentSnapshot.publish_time)
Index("idx_comments_content_id", CommentSnapshot.content_id)
Index("idx_comments_fetched_at", CommentSnapshot.fetched_at)
Index("idx_candidate_decisions_content_id", CandidateDecision.content_id, CandidateDecision.evaluated_at.desc())
Index("idx_candidate_decisions_bucket", CandidateDecision.candidate_bucket)
Index("idx_creator_monitors_enabled", CreatorMonitor.enabled)
Index("idx_creator_monitors_group_key", CreatorMonitor.monitor_group_key)
Index("idx_users_status", User.status)
Index("idx_employees_user_id", Employee.user_id)
Index("idx_agents_employee_id", LocalAgent.employee_id)
Index("idx_platform_accounts_employee_id", PlatformAccount.employee_id)
Index("idx_platform_accounts_business_type_id", PlatformAccount.business_account_type_id)
Index("idx_account_agent_bindings_account", AccountAgentBinding.account_id)
Index("idx_account_agent_bindings_agent", AccountAgentBinding.agent_id)
Index("idx_account_agent_bindings_employee", AccountAgentBinding.employee_id)
Index("idx_agent_account_snapshots_agent", AgentAccountSnapshot.agent_id)
Index("idx_benchmark_groups_enabled", BenchmarkGroup.enabled)
Index("idx_benchmark_members_group_id", BenchmarkGroupMember.benchmark_group_id)
Index("idx_task_templates_type_enabled", TaskTemplate.template_type, TaskTemplate.enabled)
Index("idx_task_runs_template_created", TaskRun.task_template_id, TaskRun.created_at.desc())
Index("idx_task_runs_status", TaskRun.status)
Index("idx_task_schedules_template_id", TaskSchedule.task_template_id)
Index("idx_task_schedules_enabled", TaskSchedule.enabled)
Index("idx_risk_policies_enabled", RiskPolicy.enabled)
Index("idx_content_workflow_status", ContentWorkflowState.workflow_status)
Index("idx_content_workflow_assignee", ContentWorkflowState.assigned_to_user_id)
Index("idx_content_assignments_content_id", ContentAssignment.content_id)
Index("idx_content_notes_content_id", ContentOperatorNote.content_id)
