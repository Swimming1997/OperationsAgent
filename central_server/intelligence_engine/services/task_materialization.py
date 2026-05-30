from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import (
    AccountAgentBinding,
    AccountSession,
    BenchmarkGroup,
    BenchmarkGroupMember,
    BusinessAccountType,
    BusinessAccountTypeBenchmarkGroup,
    BusinessAccountTypeRuleSet,
    CreatorMonitor,
    Job,
    KeywordRuleSet,
    LocalAgent,
    PlatformAccount,
    TaskRun,
    TaskSchedule,
    TaskTemplate,
    utcnow,
)
from intelligence_engine.domain.enums import AgentStatus, JobStatus, JobType, Platform, SessionStatus, TaskRunStatus, TaskRunTriggerType, TaskScheduleType, TaskTemplateType, AccountRole
from intelligence_engine.domain.job_priority import priority_for_task_run_trigger
from intelligence_engine.api.task_template_access import benchmark_group_binding_status, rule_set_binding_status
from intelligence_engine.domain.product_schemas import (
    CreatorMonitorTaskPayload,
    CreatorMonitorTemplateConfig,
    KeywordSearchTaskPayload,
    KeywordSearchTemplateConfig,
    RecommendationFeedTaskPayload,
    RecommendationFeedTemplateConfig,
)
from intelligence_engine.services.task_template_config import (
    LEGACY_TEMPLATE_DEFAULTS,
    parse_template_config_dict,
    strip_legacy_template_config_keys,
)
from intelligence_engine.storage.repositories.creator_repository import CreatorMonitorRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository


def enum_value(value):
    return getattr(value, "value", value)


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _latest_finished_at(jobs: list[Job]) -> datetime:
    finished = [_coerce_utc(job.finished_at) for job in jobs if job.finished_at]
    return max(finished, default=utcnow())


class TaskMaterializationService:
    def __init__(self, db: Session):
        self.db = db

    def validate_template_config(self, template_type: str, config: dict[str, Any]) -> dict[str, Any]:
        normalized = strip_legacy_template_config_keys(parse_template_config_dict(config))
        if template_type == TaskTemplateType.RECOMMENDATION_FEED_TASK.value:
            return RecommendationFeedTemplateConfig.model_validate(normalized).model_dump(mode="json")
        if template_type == TaskTemplateType.CREATOR_MONITOR_TASK.value:
            return CreatorMonitorTemplateConfig.model_validate(normalized).model_dump(mode="json")
        if template_type == TaskTemplateType.KEYWORD_SEARCH_TASK.value:
            return KeywordSearchTemplateConfig.model_validate(normalized).model_dump(mode="json")
        raise ValueError(f"unsupported task template type: {template_type}")

    def read_template_config(self, template_type: str, config: Any) -> dict[str, Any]:
        """Validate stored config for API reads; tolerate legacy payloads missing new fields."""
        normalized = strip_legacy_template_config_keys(parse_template_config_dict(config))
        try:
            return self.validate_template_config(template_type, normalized)
        except ValidationError:
            merged = {**LEGACY_TEMPLATE_DEFAULTS.get(template_type, {}), **normalized}
            try:
                return self.validate_template_config(template_type, merged)
            except ValidationError:
                return merged

    def validate_runtime_payload(self, template_type: str, config: dict[str, Any], *, executor_account_id: str) -> dict[str, Any]:
        runtime = {**(config or {}), "executor_account_id": executor_account_id}
        if template_type == TaskTemplateType.RECOMMENDATION_FEED_TASK.value:
            return RecommendationFeedTaskPayload.model_validate(runtime).model_dump(mode="json")
        if template_type == TaskTemplateType.CREATOR_MONITOR_TASK.value:
            return CreatorMonitorTaskPayload.model_validate(runtime).model_dump(mode="json")
        if template_type == TaskTemplateType.KEYWORD_SEARCH_TASK.value:
            return KeywordSearchTaskPayload.model_validate(runtime).model_dump(mode="json")
        raise ValueError(f"unsupported task template type: {template_type}")

    def validate_template_payload(self, template_type: str, config: dict[str, Any]) -> dict[str, Any]:
        """Backward-compatible alias for stored template config validation."""
        return self.validate_template_config(template_type, config)

    def materialize_template(self, template: TaskTemplate, *, executor_account_id: str) -> list[str]:
        return self.materialize_template_for_run(
            template,
            executor_account_id=executor_account_id,
            task_run_id=None,
        )

    def create_task_run(
        self,
        template: TaskTemplate,
        *,
        trigger_type: TaskRunTriggerType,
        executor_account_id: str,
        requested_by_user_id: str | None = None,
        task_schedule_id: str | None = None,
    ) -> TaskRun:
        run = TaskRun(
            task_template_id=template.id,
            trigger_type=enum_value(trigger_type),
            requested_by_user_id=requested_by_user_id,
            executor_account_id=executor_account_id,
            task_schedule_id=task_schedule_id,
            status=TaskRunStatus.MATERIALIZED.value,
            result_summary_json={},
            error_summary_json={},
        )
        self.db.add(run)
        self.db.flush()
        return run

    def materialize_template_for_run(
        self,
        template: TaskTemplate,
        *,
        executor_account_id: str,
        task_run_id: str | None,
        trigger_type: TaskRunTriggerType | None = None,
    ) -> list[str]:
        config = self.validate_runtime_payload(
            template.template_type,
            template.config_json or {},
            executor_account_id=executor_account_id,
        )
        priority = priority_for_task_run_trigger(trigger_type) if task_run_id and trigger_type else None
        if template.template_type == TaskTemplateType.RECOMMENDATION_FEED_TASK.value:
            return self._materialize_recommendation_feed(config, task_run_id=task_run_id, priority=priority, trigger_type=trigger_type)
        if template.template_type == TaskTemplateType.CREATOR_MONITOR_TASK.value:
            return self._materialize_creator_monitor(config, task_run_id=task_run_id, priority=priority, trigger_type=trigger_type)
        if template.template_type == TaskTemplateType.KEYWORD_SEARCH_TASK.value:
            return self._materialize_keyword_search(config, task_run_id=task_run_id, priority=priority, trigger_type=trigger_type)
        raise ValueError(f"unsupported task template type: {template.template_type}")

    def run_template(
        self,
        template: TaskTemplate,
        *,
        executor_account_id: str,
        trigger_type: TaskRunTriggerType,
        requested_by_user_id: str | None = None,
        task_schedule_id: str | None = None,
    ) -> tuple[TaskRun, list[str]]:
        run = self.create_task_run(
            template,
            trigger_type=trigger_type,
            executor_account_id=executor_account_id,
            requested_by_user_id=requested_by_user_id,
            task_schedule_id=task_schedule_id,
        )
        try:
            job_ids = self.materialize_template_for_run(
                template,
                executor_account_id=executor_account_id,
                task_run_id=run.id,
                trigger_type=trigger_type,
            )
        except Exception as exc:
            run.status = TaskRunStatus.FAILED.value
            run.error_summary_json = {"message": str(exc)}
            run.finished_at = utcnow()
            self.db.flush()
            raise
        self.refresh_task_run(run)
        return run, job_ids

    def materialize_due_schedules(self, *, now=None) -> list[dict[str, Any]]:
        now = now or utcnow()
        schedules = list(
            self.db.scalars(
                select(TaskSchedule)
                .where(TaskSchedule.enabled.is_(True))
                .where(TaskSchedule.next_run_at.is_not(None))
                .where(TaskSchedule.next_run_at <= now)
                .order_by(TaskSchedule.next_run_at.asc())
            )
        )
        results = []
        for schedule in schedules:
            template = self.db.get(TaskTemplate, schedule.task_template_id)
            if not template or not template.enabled:
                continue
            if not schedule.executor_account_id:
                continue
            run, job_ids = self.run_template(
                template,
                executor_account_id=schedule.executor_account_id,
                trigger_type=TaskRunTriggerType.SCHEDULED,
                task_schedule_id=schedule.id,
            )
            schedule.last_materialized_at = now
            schedule.last_run_at = now
            schedule.next_run_at = self._next_run_at(schedule, now)
            results.append({"schedule_id": schedule.id, "template_id": template.id, "task_run_id": run.id, "job_ids": job_ids})
        self.db.flush()
        return results

    def refresh_active_task_runs(self) -> int:
        """刷新可能过期的运行批次聚合状态（有活跃 Job 或批次仍为进行中）。"""
        active_job_statuses = (
            JobStatus.PENDING.value,
            JobStatus.CLAIMED.value,
            JobStatus.RUNNING.value,
        )
        run_ids: set[str] = set(
            self.db.scalars(
                select(Job.task_run_id)
                .where(Job.task_run_id.is_not(None), Job.status.in_(active_job_statuses))
                .distinct()
            )
        )
        open_run_statuses = (
            TaskRunStatus.MATERIALIZED.value,
            TaskRunStatus.QUEUED.value,
            TaskRunStatus.RUNNING.value,
        )
        run_ids.update(self.db.scalars(select(TaskRun.id).where(TaskRun.status.in_(open_run_statuses))))
        refreshed = 0
        for run_id in run_ids:
            run = self.db.get(TaskRun, run_id)
            if run:
                self.refresh_task_run(run)
                refreshed += 1
        return refreshed

    def refresh_task_run(self, run: TaskRun) -> TaskRun:
        jobs = list(self.db.scalars(select(Job).where(Job.task_run_id == run.id).order_by(Job.created_at.asc())))
        pending_statuses = {JobStatus.PENDING.value, JobStatus.CLAIMED.value}
        running_statuses = {JobStatus.RUNNING.value}
        success_statuses = {JobStatus.SUCCESS.value, JobStatus.PARTIAL_SUCCESS.value}
        failed_statuses = {JobStatus.FAILED.value, JobStatus.CANCELLED.value}
        run.jobs_total = len(jobs)
        run.jobs_pending = sum(1 for job in jobs if job.status in pending_statuses)
        run.jobs_running = sum(1 for job in jobs if job.status in running_statuses)
        run.jobs_success = sum(1 for job in jobs if job.status in success_statuses)
        run.jobs_failed = sum(1 for job in jobs if job.status in failed_statuses)
        run.result_summary_json = summarize_jobs(jobs)
        run.error_summary_json = summarize_errors(jobs)
        terminal_count = run.jobs_success + run.jobs_failed
        if not jobs:
            if run.status != TaskRunStatus.FAILED.value:
                run.status = TaskRunStatus.FAILED.value
                run.error_summary_json = {"message": "未生成 Job"}
                run.finished_at = run.finished_at or utcnow()
        elif run.jobs_running:
            run.status = TaskRunStatus.RUNNING.value
            run.finished_at = None
        elif run.jobs_pending:
            run.status = TaskRunStatus.QUEUED.value
            run.finished_at = None
        elif terminal_count == len(jobs):
            if run.jobs_failed and run.jobs_success:
                run.status = TaskRunStatus.PARTIAL_SUCCESS.value
            elif run.jobs_failed:
                run.status = TaskRunStatus.FAILED.value
            elif any(job.status == JobStatus.PARTIAL_SUCCESS.value for job in jobs):
                run.status = TaskRunStatus.PARTIAL_SUCCESS.value
            else:
                run.status = TaskRunStatus.SUCCESS.value
            run.finished_at = run.finished_at or _latest_finished_at(jobs)
        self.db.flush()
        return run

    def _materialize_recommendation_feed(
        self,
        config: dict[str, Any],
        *,
        task_run_id: str | None,
        priority: int | None = None,
        trigger_type: TaskRunTriggerType | None = None,
    ) -> list[str]:
        payload = RecommendationFeedTaskPayload.model_validate(config)
        account = self._get_account(payload.executor_account_id)
        self._ensure_intelligence_collector(account, JobType.FEED_COLLECT.value)
        self._ensure_rule_set_allowed(account, payload.rule_set_id)
        job_payload = {
            "platform": account.platform,
            "account_id": account.id,
            "feed_type": enum_value(payload.feed_type),
            "target_count": payload.target_count,
            "refresh_rounds": payload.refresh_rounds,
            "per_round_scroll_target": payload.per_round_scroll_target,
            "rule_set_id": payload.rule_set_id,
            "behavior_profile_id": payload.behavior_profile_id,
            "network_egress_profile_id": payload.network_egress_profile_id,
            "risk_policy_id": payload.risk_policy_id,
            "materialized_from_task": True,
        }
        if trigger_type:
            job_payload["task_run_trigger"] = enum_value(trigger_type)
        job = JobRepository(self.db).create_job(
            job_type=JobType.FEED_COLLECT,
            account_id=account.id,
            local_agent_id=account.default_agent_id,
            task_run_id=task_run_id,
            payload=job_payload,
            priority=priority or 100,
        )
        return [job.id]

    def _materialize_creator_monitor(
        self,
        config: dict[str, Any],
        *,
        task_run_id: str | None,
        priority: int | None = None,
        trigger_type: TaskRunTriggerType | None = None,
    ) -> list[str]:
        payload = CreatorMonitorTaskPayload.model_validate(config)
        account = self._get_account(payload.executor_account_id)
        self._ensure_intelligence_collector(account, JobType.CREATOR_MONITOR.value)
        self._ensure_rule_set_allowed(account, payload.rule_set_id)
        self._ensure_benchmark_group_allowed(account, payload.benchmark_group_id)
        members = list(
            self.db.scalars(
                select(BenchmarkGroupMember)
                .where(BenchmarkGroupMember.benchmark_group_id == payload.benchmark_group_id)
                .where(BenchmarkGroupMember.enabled.is_(True))
                .order_by(BenchmarkGroupMember.created_at.asc())
            )
        )
        job_ids: list[str] = []
        for member in members:
            monitor = self._ensure_member_monitor(member)
            job = JobRepository(self.db).create_job(
                job_type=JobType.CREATOR_MONITOR,
                account_id=account.id,
                local_agent_id=account.default_agent_id,
                creator_monitor_id=monitor.id,
                task_run_id=task_run_id,
                payload={
                    "creator_monitor_id": monitor.id,
                    "platform": monitor.platform,
                    "creator_platform_id": monitor.creator_platform_id,
                    "creator_profile_url": (monitor.metadata_json or {}).get("creator_profile_url") or (monitor.metadata_json or {}).get("profile_url"),
                    "platform_context": (monitor.metadata_json or {}).get("platform_context", {}),
                    "max_latest_items": payload.max_latest_items,
                    "rule_set_id": payload.rule_set_id,
                    "auto_detail_fetch": payload.auto_detail_fetch,
                    "behavior_profile_id": payload.behavior_profile_id,
                    "network_egress_profile_id": payload.network_egress_profile_id,
                    "risk_policy_id": payload.risk_policy_id,
                    "executor_account_id": account.id,
                    "benchmark_group_id": payload.benchmark_group_id,
                    "materialized_from_task": True,
                    **({"task_run_trigger": enum_value(trigger_type)} if trigger_type else {}),
                },
                priority=priority or 100,
            )
            job_ids.append(job.id)
        return job_ids

    def _materialize_keyword_search(
        self,
        config: dict[str, Any],
        *,
        task_run_id: str | None,
        priority: int | None = None,
        trigger_type: TaskRunTriggerType | None = None,
    ) -> list[str]:
        payload = KeywordSearchTaskPayload.model_validate(config)
        account = self._get_account(payload.executor_account_id)
        self._ensure_intelligence_collector(account, JobType.SEARCH_COLLECT.value)
        self._ensure_rule_set_allowed(account, payload.rule_set_id)
        job = JobRepository(self.db).create_job(
            job_type=JobType.SEARCH_COLLECT,
            account_id=account.id,
            local_agent_id=account.default_agent_id,
            task_run_id=task_run_id,
            payload={
                "platform": enum_value(payload.platform),
                "executor_account_id": account.id,
                "keywords": payload.keywords,
                "keyword_group": payload.keyword_group,
                "max_items": payload.max_items,
                "search_sort": enum_value(payload.search_sort),
                "note_type": enum_value(payload.note_type),
                "publish_time": enum_value(payload.publish_time),
                "search_scope": enum_value(payload.search_scope),
                "location_filter": enum_value(payload.location_filter),
                "per_keyword_limit": payload.per_keyword_limit,
                "collect_suggestions_first": payload.collect_suggestions_first,
                "rule_set_id": payload.rule_set_id,
                "behavior_profile_id": payload.behavior_profile_id,
                "network_egress_profile_id": payload.network_egress_profile_id,
                "risk_policy_id": payload.risk_policy_id,
                "materialized_from_task": True,
                **({"task_run_trigger": enum_value(trigger_type)} if trigger_type else {}),
            },
            priority=priority or 100,
        )
        return [job.id]

    def _get_account(self, account_id: str) -> PlatformAccount:
        account = self.db.get(PlatformAccount, account_id)
        if not account:
            raise ValueError(f"executor account not found: {account_id}")
        return account

    def _ensure_intelligence_collector(self, account: PlatformAccount, job_type: str) -> None:
        role = getattr(account, "account_role", None) or AccountRole.INTELLIGENCE_COLLECTOR.value
        if role != AccountRole.INTELLIGENCE_COLLECTOR.value:
            raise ValueError(f"account {account.id} role {role} cannot run {job_type}")

    def _ensure_rule_set_allowed(self, account: PlatformAccount, rule_set_id: str | None) -> None:
        ok, message = self._rule_set_binding_status(account, rule_set_id)
        if not ok:
            raise ValueError(message)

    def _rule_set_binding_status(self, account: PlatformAccount | None, rule_set_id: str | None) -> tuple[bool, str]:
        if not rule_set_id:
            return True, "未选择规则集"
        rule_set = self.db.get(KeywordRuleSet, rule_set_id)
        if not rule_set:
            return False, f"规则集不存在: {rule_set_id}"
        if not account:
            return False, "缺少执行账号，无法校验规则集绑定"
        if not account.business_account_type_id:
            return False, f"执行账号 {account.display_name or account.id} 未设置业务类型，不能使用规则集 {rule_set.name}"
        binding = self.db.scalar(
            select(BusinessAccountTypeRuleSet).where(
                BusinessAccountTypeRuleSet.business_account_type_id == account.business_account_type_id,
                BusinessAccountTypeRuleSet.rule_set_id == rule_set_id,
            )
        )
        business_type = self.db.get(BusinessAccountType, account.business_account_type_id)
        business_type_name = business_type.name if business_type else account.business_account_type_id
        if not binding:
            return False, f"规则集 {rule_set.name} 未绑定到业务类型 {business_type_name}"
        return True, f"规则集 {rule_set.name} 已绑定到业务类型 {business_type_name}"

    def _ensure_benchmark_group_allowed(self, account: PlatformAccount, benchmark_group_id: str | None) -> None:
        ok, message = self._benchmark_group_binding_status(account, benchmark_group_id)
        if not ok:
            raise ValueError(message)

    def _benchmark_group_binding_status(self, account: PlatformAccount | None, benchmark_group_id: str | None) -> tuple[bool, str]:
        if not benchmark_group_id:
            return False, "缺少对标账号组"
        group = self.db.get(BenchmarkGroup, benchmark_group_id)
        if not group:
            return False, f"对标账号组不存在: {benchmark_group_id}"
        if not account:
            return False, "缺少执行账号，无法校验对标账号组绑定"
        if not account.business_account_type_id:
            return False, f"执行账号 {account.display_name or account.id} 未设置业务类型，不能使用对标账号组 {group.name}"
        binding = self.db.scalar(
            select(BusinessAccountTypeBenchmarkGroup).where(
                BusinessAccountTypeBenchmarkGroup.business_account_type_id == account.business_account_type_id,
                BusinessAccountTypeBenchmarkGroup.benchmark_group_id == benchmark_group_id,
            )
        )
        business_type = self.db.get(BusinessAccountType, account.business_account_type_id)
        business_type_name = business_type.name if business_type else account.business_account_type_id
        if not binding:
            return False, f"对标账号组 {group.name} 未绑定到业务类型 {business_type_name}"
        return True, f"对标账号组 {group.name} 已绑定到业务类型 {business_type_name}"

    def _ensure_member_monitor(self, member: BenchmarkGroupMember) -> CreatorMonitor:
        if member.creator_monitor_id:
            monitor = self.db.get(CreatorMonitor, member.creator_monitor_id)
            if monitor:
                return monitor
        if not member.creator_platform_id:
            raise ValueError(f"benchmark group member lacks creator_monitor_id and creator_platform_id: {member.id}")
        monitor = self.db.scalar(
            select(CreatorMonitor).where(
                CreatorMonitor.platform == member.platform,
                CreatorMonitor.creator_platform_id == member.creator_platform_id,
            )
        )
        if not monitor:
            monitor = CreatorMonitorRepository(self.db).create_monitor(
                platform=member.platform or Platform.XHS.value,
                creator_platform_id=member.creator_platform_id,
                creator_display_name=member.display_name,
                monitor_group_key=member.benchmark_group_id,
                mapped_business_account_type=None,
                check_interval_seconds=900,
            )
            metadata = dict(monitor.metadata_json or {})
            if member.creator_profile_url:
                metadata["creator_profile_url"] = member.creator_profile_url
            if member.platform_context_json:
                metadata["platform_context"] = member.platform_context_json
            monitor.metadata_json = metadata
        member.creator_monitor_id = monitor.id
        return monitor

    def _next_run_at(self, schedule: TaskSchedule, now):
        if schedule.schedule_type == TaskScheduleType.INTERVAL_SECONDS.value and schedule.interval_seconds:
            return now + timedelta(seconds=schedule.interval_seconds)
        if schedule.schedule_type == TaskScheduleType.MANUAL.value:
            return None
        return schedule.next_run_at

    def template_readiness_checks(self, template: TaskTemplate) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        business_type_id = template.business_account_type_id
        checks.append(
            {
                "key": "business_account_type",
                "ok": bool(business_type_id),
                "message": "已设置业务类型" if business_type_id else "缺少业务类型",
            }
        )
        try:
            config = self.validate_template_config(template.template_type, template.config_json or {})
        except Exception as exc:
            return checks + [{"key": "template_config", "ok": False, "message": f"模板配置不完整: {exc}"}]

        rule_set_id = config.get("rule_set_id")
        if rule_set_id:
            ok, message = rule_set_binding_status(self.db, business_account_type_id=business_type_id, rule_set_id=rule_set_id)
            checks.append({"key": "rule_set_business_type_binding", "ok": ok, "message": message})

        if template.template_type == TaskTemplateType.CREATOR_MONITOR_TASK.value:
            group_id = config.get("benchmark_group_id")
            ok, message = benchmark_group_binding_status(
                self.db,
                business_account_type_id=business_type_id,
                benchmark_group_id=group_id,
            )
            checks.append({"key": "benchmark_group_business_type_binding", "ok": ok, "message": message})
            group = self.db.get(BenchmarkGroup, group_id) if group_id else None
            member_count = 0
            if group:
                member_count = self.db.scalar(
                    select(func.count(BenchmarkGroupMember.id))
                    .where(BenchmarkGroupMember.benchmark_group_id == group.id)
                    .where(BenchmarkGroupMember.enabled.is_(True))
                ) or 0
            checks.append(
                {
                    "key": "benchmark_group_members",
                    "ok": bool(group and group.enabled and member_count > 0),
                    "message": f"对标组有效，含 {member_count} 个成员"
                    if group and group.enabled and member_count > 0
                    else "对标组为空或未启用",
                }
            )
        if template.template_type == TaskTemplateType.RECOMMENDATION_FEED_TASK.value:
            ok = bool(
                config.get("feed_type")
                and config.get("target_count")
                and config.get("refresh_rounds")
                and config.get("per_round_scroll_target")
            )
            checks.append(
                {
                    "key": "recommendation_feed_config",
                    "ok": ok,
                    "message": "推荐页任务关键字段完整" if ok else "推荐页任务关键字段不完整",
                }
            )
        return checks

    def run_readiness_checks(self, template: TaskTemplate, executor_account_id: str) -> list[dict[str, Any]]:
        checks = list(self.template_readiness_checks(template))
        account = self.db.get(PlatformAccount, executor_account_id)
        checks.append({"key": "executor_account", "ok": bool(account), "message": "执行账号存在" if account else "执行账号不存在"})
        if account and template.business_account_type_id and account.business_account_type_id != template.business_account_type_id:
            checks.append(
                {
                    "key": "executor_account_business_type",
                    "ok": False,
                    "message": "执行账号业务类型与模板不一致",
                }
            )
        pool_agents = self._agent_pool_for_account(account) if account else []
        checks.append(
            {
                "key": "agent_pool_bound",
                "ok": bool(pool_agents),
                "message": f"账号已绑定/可用 Agent {len(pool_agents)} 台" if pool_agents else "账号未绑定 Agent",
            }
        )
        online_agents = [agent for agent in pool_agents if agent.status == AgentStatus.ONLINE.value]
        checks.append(
            {
                "key": "agent_pool_online",
                "ok": bool(online_agents),
                "message": f"在线 Agent {len(online_agents)} 台" if online_agents else "绑定池中暂无在线 Agent",
            }
        )
        ready_session = None
        if account and pool_agents:
            ready_session = self.db.scalar(
                select(AccountSession)
                .where(AccountSession.account_id == account.id)
                .where(AccountSession.local_agent_id.in_([item.id for item in pool_agents]))
                .where(AccountSession.status == SessionStatus.READY.value)
                .order_by(AccountSession.last_validated_at.desc().nullslast(), AccountSession.created_at.desc())
                .limit(1)
            )
        checks.append(
            {
                "key": "session_pool_ready",
                "ok": bool(ready_session),
                "message": "绑定池存在 ready 会话" if ready_session else "绑定池暂无 ready 会话",
            }
        )

        expected_job_type = expected_job_type_for_template(template.template_type)
        agent = online_agents[0] if online_agents else (pool_agents[0] if pool_agents else None)
        capabilities = agent.capabilities_json if agent else {}
        declared_job_types = list_declared_job_types(capabilities)
        supports = agent_supports_job_type(capabilities, expected_job_type) if expected_job_type else False
        agent_label = f"{agent.device_name or '未命名 Agent'} [{agent.id}]" if agent else "未绑定"
        if supports:
            support_message = f"Agent 支持 {expected_job_type}（{agent_label}）"
        else:
            declared_text = ", ".join(declared_job_types) if declared_job_types else "无 job_types/tasks 声明"
            support_message = f"Agent 不支持 {expected_job_type}（{agent_label}；已声明: {declared_text}）"
            legacy_runner = capabilities.get("runner") if isinstance(capabilities.get("runner"), str) else None
            legacy_probe = capabilities.get("probe") if isinstance(capabilities.get("probe"), str) else None
            if legacy_runner or legacy_probe:
                legacy_kind = legacy_runner or legacy_probe
                support_message += f"；当前绑定的是旧脚本 Agent（{legacy_kind}），请在账号管理改绑 Local Agent Runtime V1（capabilities.runtime=local_agent_runtime_v1）"
        checks.append({"key": "agent_supports_job_type", "ok": supports, "message": support_message})
        return checks

    def readiness_checks(self, template: TaskTemplate) -> list[dict[str, Any]]:
        """Template-only readiness (no executor account)."""
        return self.template_readiness_checks(template)

    def _agent_pool_for_account(self, account: PlatformAccount | None) -> list[LocalAgent]:
        if not account:
            return []
        agents_by_id: dict[str, LocalAgent] = {}
        bindings = list(
            self.db.scalars(
                select(AccountAgentBinding)
                .where(AccountAgentBinding.account_id == account.id)
                .where(AccountAgentBinding.enabled.is_(True))
                .order_by(AccountAgentBinding.updated_at.desc())
            )
        )
        for binding in bindings:
            agent = self.db.get(LocalAgent, binding.agent_id)
            if agent and agent.status != AgentStatus.RETIRED.value:
                agents_by_id[agent.id] = agent
        if account.employee_id:
            for agent in self.db.scalars(
                select(LocalAgent).where(
                    LocalAgent.employee_id == account.employee_id,
                    LocalAgent.status != AgentStatus.RETIRED.value,
                )
            ):
                agents_by_id.setdefault(agent.id, agent)
        return list(agents_by_id.values())


def expected_job_type_for_template(template_type: str) -> str | None:
    if template_type == TaskTemplateType.RECOMMENDATION_FEED_TASK.value:
        return JobType.FEED_COLLECT.value
    if template_type == TaskTemplateType.CREATOR_MONITOR_TASK.value:
        return JobType.CREATOR_MONITOR.value
    if template_type == TaskTemplateType.KEYWORD_SEARCH_TASK.value:
        return JobType.SEARCH_COLLECT.value
    return None


def list_declared_job_types(capabilities: dict[str, Any]) -> list[str]:
    declared: list[str] = []
    for key in ("job_types", "tasks", "supported_job_types"):
        value = capabilities.get(key)
        if isinstance(value, list):
            declared.extend(str(item) for item in value if item)
    if capabilities.get("xhs") is True:
        for legacy_type in (JobType.FEED_COLLECT.value, JobType.CREATOR_MONITOR.value):
            if legacy_type not in declared:
                declared.append(legacy_type)
    return list(dict.fromkeys(declared))


def agent_supports_job_type(capabilities: dict[str, Any], job_type: str | None) -> bool:
    if not job_type:
        return False
    return job_type in list_declared_job_types(capabilities)


def summarize_errors(jobs: list[Job]) -> dict[str, Any]:
    errors = [
        {"job_id": job.id, "job_type": job.job_type, "error_code": job.last_error_code, "message": job.last_error_message}
        for job in jobs
        if job.last_error_code or job.last_error_message
    ]
    return {"errors": errors, "error_count": len(errors)}


def summarize_jobs(jobs: list[Job]) -> dict[str, Any]:
    summary: dict[str, Any] = {"job_count": len(jobs)}
    feed = [job for job in jobs if job.job_type == JobType.FEED_COLLECT.value]
    creator = [job for job in jobs if job.job_type == JobType.CREATOR_MONITOR.value]
    if feed:
        feed_results = [job for job in feed if job.result_summary_json]
        sampled = sum(_first_int(job.result_summary_json, "raw_items_seen", "items_seen", "sampled_count", "normalized_items") for job in feed_results)
        inserted = sum(_first_int(job.result_summary_json, "unique_contents_inserted", "unique_contents", "ingestion_unique_count") for job in feed_results)
        detail_jobs = sum(_first_int(job.result_summary_json, "detail_jobs_enqueued", "ingestion_detail_jobs_enqueued") for job in feed_results)
        prelim_pass = sum(_first_int(job.result_summary_json, "prelim_pass_count") for job in feed_results)
        prelim_discard = sum(_first_int(job.result_summary_json, "prelim_discard_count") for job in feed_results)
        ingestion_success = sum(_first_int(job.result_summary_json, "ingestion_success_count", "normalized_items", "raw_items_seen") for job in feed_results)
        duplicate = sum(_first_int(job.result_summary_json, "duplicate_contents", "duplicate_count") for job in feed_results)
        if duplicate == 0 and ingestion_success and inserted <= ingestion_success:
            duplicate = ingestion_success - inserted
        enrichment_jobs = [job for job in jobs if job.job_type in {JobType.DETAIL_FETCH.value, JobType.COMMENT_FETCH.value}]
        enrichment_terminal = {JobStatus.SUCCESS.value, JobStatus.PARTIAL_SUCCESS.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}
        enrichment_done = sum(1 for job in enrichment_jobs if job.status in enrichment_terminal)
        enrichment_success = sum(1 for job in enrichment_jobs if job.status in {JobStatus.SUCCESS.value, JobStatus.PARTIAL_SUCCESS.value})
        summary["feed_collect"] = {
            "sampled_count": sampled,
            "inserted_count": inserted,
            "duplicate_count": duplicate,
            "detail_jobs_enqueued": detail_jobs,
            "prelim_pass_count": prelim_pass,
            "prelim_discard_count": prelim_discard,
            "enrichment_total": len(enrichment_jobs),
            "enrichment_done": enrichment_done,
            "enrichment_success": enrichment_success,
            "message": _feed_message(
                sampled,
                inserted,
                duplicate,
                detail_jobs,
                prelim_pass=prelim_pass,
                prelim_discard=prelim_discard,
                enrichment_done=enrichment_done,
                enrichment_total=len(enrichment_jobs),
                enrichment_success=enrichment_success,
            )
            if feed_results
            else "等待 Agent 执行，尚未产生结果摘要。",
        }
    if creator:
        creator_results = [job for job in creator if job.result_summary_json]
        seen = sum(_first_int(job.result_summary_json, "items_seen", "creator_items_seen") for job in creator_results)
        new_count = sum(_first_int(job.result_summary_json, "new_content_count", "new_contents_detected") for job in creator_results)
        duplicate = sum(_first_int(job.result_summary_json, "duplicate_content_count", "duplicate_count") for job in creator_results)
        detail_jobs = sum(_first_int(job.result_summary_json, "detail_job_enqueue_count", "detail_jobs_enqueued") for job in creator_results)
        summary["creator_monitor"] = {
            "seen_count": seen,
            "new_count": new_count,
            "duplicate_count": duplicate,
            "detail_jobs_enqueued": detail_jobs,
            "message": _creator_message(seen, new_count, duplicate, detail_jobs) if creator_results else "等待 Agent 执行，尚未产生结果摘要。",
        }
    search = [job for job in jobs if job.job_type == JobType.SEARCH_COLLECT.value]
    if search:
        search_results = [job for job in search if job.result_summary_json]
        keywords: list[str] = []
        per_keyword_summary: list[dict[str, Any]] = []
        for job in search_results:
            payload_keywords = (job.payload_json or {}).get("keywords") or []
            keywords.extend(payload_keywords)
            per_keyword_summary.extend((job.result_summary_json or {}).get("per_keyword_summary") or [])
        keywords = sorted({item for item in keywords if item})
        searched_keyword_count = _first_int(search_results[0].result_summary_json if search_results else {}, "searched_keyword_count") or len(keywords)
        total_items_seen = sum(_first_int(job.result_summary_json, "total_items_seen", "normalized_items", "items_seen") for job in search_results)
        new_count = sum(_first_int(job.result_summary_json, "new_content_count", "unique_contents_inserted") for job in search_results)
        duplicate = sum(_first_int(job.result_summary_json, "duplicate_content_count", "duplicate_count") for job in search_results)
        detail_jobs = sum(_first_int(job.result_summary_json, "detail_jobs_enqueued") for job in search_results)
        failed_keyword_count = sum(_first_int(job.result_summary_json, "failed_keyword_count") for job in search_results)
        summary["keyword_search"] = {
            "searched_keyword_count": searched_keyword_count,
            "keywords": keywords,
            "total_items_seen": total_items_seen,
            "new_content_count": new_count,
            "duplicate_content_count": duplicate,
            "prelim_candidate_count": sum(_first_int(job.result_summary_json, "prelim_candidate_count", "ingestion_success_count") for job in search_results),
            "detail_jobs_enqueued": detail_jobs,
            "failed_keyword_count": failed_keyword_count,
            "per_keyword_summary": per_keyword_summary,
            "message": _search_message(searched_keyword_count, total_items_seen, new_count, duplicate, detail_jobs, failed_keyword_count)
            if search_results
            else "等待 Agent 执行，尚未产生结果摘要。",
        }
    return summary


def _first_int(value: dict, *keys: str) -> int:
    for key in keys:
        raw = (value or {}).get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int):
            return raw
    return 0


def _feed_message(
    sampled: int,
    inserted: int,
    duplicate: int,
    detail_jobs: int,
    *,
    prelim_pass: int = 0,
    prelim_discard: int = 0,
    enrichment_done: int = 0,
    enrichment_total: int = 0,
    enrichment_success: int = 0,
) -> str:
    prelim_part = ""
    if prelim_pass or prelim_discard:
        prelim_part = f"，预筛建议优先 {prelim_pass} 条、低优先 {prelim_discard} 条（均会进入详情补全）"
    if enrichment_total and enrichment_done < enrichment_total:
        return (
            f"推荐流采样 {sampled or inserted} 条，新增入库 {inserted} 条，去重 {duplicate} 条{prelim_part}；"
            f"详情/评论补全进行中 {enrichment_done}/{enrichment_total}（成功 {enrichment_success}）。"
        )
    if enrichment_total:
        return (
            f"任务完成：推荐流采样 {sampled or inserted} 条，新增入库 {inserted} 条，去重 {duplicate} 条{prelim_part}；"
            f"详情/评论补全 {enrichment_success}/{enrichment_total} 成功。"
        )
    if sampled and inserted == 0:
        return f"任务执行成功，本次采样 {sampled} 条，新增 0 条，{duplicate or sampled} 条均为历史重复内容。"
    return (
        f"任务执行成功，本次采样 {sampled} 条，新增入库 {inserted} 条，去重 {duplicate} 条，"
        f"详情任务创建 {detail_jobs} 条{prelim_part}。"
    )


def _creator_message(seen: int, new_count: int, duplicate: int, detail_jobs: int) -> str:
    if seen and new_count == 0:
        return f"任务执行成功，本次查看 {seen} 条，对标账号没有新增内容，重复 {duplicate or seen} 条。"
    return f"任务执行成功，本次查看 {seen} 条，新增 {new_count} 条，重复 {duplicate} 条，详情任务创建 {detail_jobs} 条。"


def _search_message(
    keyword_count: int,
    total_items_seen: int,
    new_count: int,
    duplicate: int,
    detail_jobs: int,
    failed_keyword_count: int,
) -> str:
    failed_part = f"，{failed_keyword_count} 个关键词失败" if failed_keyword_count else ""
    return (
        f"搜索完成：{keyword_count} 个关键词，共看到 {total_items_seen} 条，"
        f"新增 {new_count} 条，重复 {duplicate} 条，详情任务 {detail_jobs} 条{failed_part}。"
    )
