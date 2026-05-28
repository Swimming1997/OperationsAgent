from collections.abc import Sequence

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import (
    AccountAgentBinding,
    AccountSession,
    BehaviorProfile,
    BenchmarkGroup,
    BenchmarkGroupMember,
    BusinessAccountType,
    BusinessAccountTypeBenchmarkGroup,
    BusinessAccountTypeRuleSet,
    Employee,
    LocalAgent,
    NetworkEgressProfile,
    PlatformAccount,
    RiskPolicy,
    KeywordRuleSet,
    KeywordRule,
    Role,
    TaskSchedule,
    TaskTemplate,
    User,
    UserRole,
)
from intelligence_engine.domain.enums import UserRoleName


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def ensure_default_roles(self) -> list[Role]:
        roles: list[Role] = []
        existing = {role.name: role for role in self.db.scalars(select(Role)).all()}
        for role_name in UserRoleName:
            role = existing.get(role_name.value)
            if not role:
                role = Role(name=role_name.value, description=f"{role_name.value} role")
                self.db.add(role)
                self.db.flush()
            roles.append(role)
        return roles

    def create_user(
        self,
        *,
        username: str,
        display_name: str,
        email: str | None,
        password_hash: str | None,
        role_names: Sequence[str],
        metadata: dict,
    ) -> User:
        self.ensure_default_roles()
        user = User(
            username=username,
            display_name=display_name,
            email=email,
            password_hash=password_hash,
            metadata_json=metadata,
        )
        self.db.add(user)
        self.db.flush()
        self.set_user_roles(user, role_names)
        return user

    def set_user_roles(self, user: User, role_names: Sequence[str]) -> None:
        if not role_names:
            return
        roles = list(self.db.scalars(select(Role).where(Role.name.in_(list(role_names)))))
        for role in roles:
            exists = self.db.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id))
            if not exists:
                self.db.add(UserRole(user_id=user.id, role_id=role.id))
        self.db.flush()

    def list_users(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.created_at.desc())))

    def get_user_by_username(self, username: str) -> User | None:
        return self.db.scalar(select(User).where(User.username == username))

    def get_user(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def get_employee_for_user(self, user_id: str) -> Employee | None:
        return self.db.scalar(select(Employee).where(Employee.user_id == user_id))

    def update_user(
        self,
        user: User,
        *,
        display_name: str | None = None,
        email: str | None = None,
        status: str | None = None,
        role_names: Sequence[str] | None = None,
    ) -> User:
        if display_name is not None:
            user.display_name = display_name
        if email is not None:
            user.email = email
        if status is not None:
            user.status = status
        self.db.flush()
        if role_names is not None:
            self.set_user_roles(user, role_names)
        return user

    def set_password(self, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        self.db.flush()
        return user

    def create_employee_with_user(
        self,
        *,
        username: str,
        display_name: str,
        email: str | None,
        password_hash: str,
        role_name: str,
        employee_status: str = "active",
    ) -> tuple[User, Employee]:
        user = self.create_user(
            username=username,
            display_name=display_name,
            email=email,
            password_hash=password_hash,
            role_names=[role_name],
            metadata={},
        )
        employee = self.create_employee(
            user_id=user.id,
            display_name=display_name,
            email=email,
            status=employee_status,
        )
        return user, employee

    def employee_account_counts(self) -> dict[str, int]:
        rows = self.db.execute(
            select(PlatformAccount.employee_id, func.count(PlatformAccount.id))
            .where(PlatformAccount.employee_id.is_not(None))
            .group_by(PlatformAccount.employee_id)
        )
        return {employee_id: count for employee_id, count in rows if employee_id}

    def employee_agent_counts(self) -> dict[str, int]:
        rows = self.db.execute(
            select(LocalAgent.employee_id, func.count(LocalAgent.id))
            .where(LocalAgent.employee_id.is_not(None))
            .group_by(LocalAgent.employee_id)
        )
        return {employee_id: count for employee_id, count in rows if employee_id}

    def user_role_names(self, user_id: str) -> list[str]:
        stmt = select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        return list(self.db.scalars(stmt))

    def create_employee(self, *, user_id: str | None, display_name: str, email: str | None, status: str) -> Employee:
        employee = Employee(user_id=user_id, display_name=display_name, email=email, status=status)
        self.db.add(employee)
        self.db.flush()
        return employee

    def list_employees(self) -> list[Employee]:
        return list(self.db.scalars(select(Employee).order_by(Employee.created_at.desc())))

    def list_agents(self, *, employee_id: str | None = None, status: str | None = None) -> list[LocalAgent]:
        stmt = select(LocalAgent)
        if employee_id:
            stmt = stmt.where(LocalAgent.employee_id == employee_id)
        if status:
            stmt = stmt.where(LocalAgent.status == status)
        return list(self.db.scalars(stmt.order_by(LocalAgent.last_heartbeat_at.desc().nullslast(), LocalAgent.created_at.desc())))

    def list_bindable_agents_for_employee(self, employee_id: str) -> list[LocalAgent]:
        """本运营已绑定 + 中央未绑定运营（employee_id 为空）的设备，供登记与选机。"""
        from sqlalchemy import or_

        from intelligence_engine.services.agent_selection import sort_agents_for_display

        agents = list(
            self.db.scalars(
                select(LocalAgent)
                .where(
                    or_(
                        LocalAgent.employee_id == employee_id,
                        LocalAgent.employee_id.is_(None),
                    )
                )
                .order_by(LocalAgent.last_heartbeat_at.desc().nullslast())
            )
        )
        visible = [agent for agent in agents if agent.status != "retired"]
        return sort_agents_for_display(visible)

    def list_accounts(
        self,
        *,
        employee_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        business_account_type_id: str | None = None,
    ) -> list[PlatformAccount]:
        stmt = select(PlatformAccount)
        if employee_id:
            stmt = stmt.where(PlatformAccount.employee_id == employee_id)
        if platform:
            stmt = stmt.where(PlatformAccount.platform == platform)
        if status:
            stmt = stmt.where(PlatformAccount.status == status)
        if business_account_type_id:
            stmt = stmt.where(PlatformAccount.business_account_type_id == business_account_type_id)
        return list(self.db.scalars(stmt.order_by(PlatformAccount.created_at.desc())))

    def create_account(
        self,
        *,
        employee_id: str | None,
        platform: str,
        display_name: str,
        external_account_id: str | None,
        business_account_type: str | None,
        business_account_type_id: str | None,
        default_agent_id: str | None = None,
        metadata: dict,
        account_role: str = "intelligence_collector",
        health_status: str = "healthy",
    ) -> PlatformAccount:
        account = PlatformAccount(
            employee_id=employee_id,
            platform=platform,
            display_name=display_name,
            external_account_id=external_account_id,
            business_account_type=business_account_type,
            business_account_type_id=business_account_type_id,
            metadata_json=metadata,
            auth_status="not_logged_in",
            account_role=account_role,
            health_status=health_status,
        )
        self.db.add(account)
        self.db.flush()
        account.profile_key = f"accounts/{account.id}"
        if default_agent_id:
            self.ensure_account_agent_binding(account_id=account.id, agent_id=default_agent_id, employee_id=employee_id)
        self.db.flush()
        return account

    def update_account(self, account: PlatformAccount, **values) -> PlatformAccount:
        metadata = values.pop("metadata", None)
        default_agent_id_marker = object()
        default_agent_id = values.pop("default_agent_id", default_agent_id_marker)
        for key, value in values.items():
            if value is not None:
                setattr(account, key, value)
        if default_agent_id is not default_agent_id_marker:
            account.default_agent_id = default_agent_id
        if metadata is not None:
            account.metadata_json = metadata
        self.db.flush()
        return account

    def list_account_agent_bindings(self, account_id: str) -> list[AccountAgentBinding]:
        return list(
            self.db.scalars(
                select(AccountAgentBinding)
                .where(AccountAgentBinding.account_id == account_id)
                .where(AccountAgentBinding.enabled.is_(True))
                .order_by(AccountAgentBinding.updated_at.desc())
            )
        )

    def list_agent_bindings_for_employee(self, employee_id: str) -> list[AccountAgentBinding]:
        return list(
            self.db.scalars(
                select(AccountAgentBinding)
                .where(AccountAgentBinding.employee_id == employee_id)
                .where(AccountAgentBinding.enabled.is_(True))
            )
        )

    def ensure_account_agent_binding(
        self,
        *,
        account_id: str,
        agent_id: str,
        employee_id: str | None,
    ) -> AccountAgentBinding:
        binding = self.db.scalar(
            select(AccountAgentBinding).where(
                AccountAgentBinding.account_id == account_id,
                AccountAgentBinding.agent_id == agent_id,
            )
        )
        if binding:
            binding.enabled = True
            binding.employee_id = employee_id
            self.db.flush()
            return binding
        binding = AccountAgentBinding(account_id=account_id, agent_id=agent_id, employee_id=employee_id, enabled=True)
        self.db.add(binding)
        self.db.flush()
        return binding

    def disable_account_agent_binding(self, *, account_id: str, agent_id: str) -> None:
        binding = self.db.scalar(
            select(AccountAgentBinding).where(
                AccountAgentBinding.account_id == account_id,
                AccountAgentBinding.agent_id == agent_id,
            )
        )
        if binding:
            binding.enabled = False
            self.db.flush()

    def latest_session_status(self, account_id: str) -> str | None:
        stmt = (
            select(AccountSession.status)
            .where(AccountSession.account_id == account_id)
            .order_by(AccountSession.last_validated_at.desc().nullslast(), AccountSession.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def create_business_account_type(self, *, name: str, description: str | None, enabled: bool) -> BusinessAccountType:
        item = BusinessAccountType(name=name, description=description, enabled=enabled)
        self.db.add(item)
        self.db.flush()
        return item

    def list_business_account_types(self) -> list[BusinessAccountType]:
        return list(self.db.scalars(select(BusinessAccountType).order_by(BusinessAccountType.created_at.desc())))

    def update_business_account_type(self, item: BusinessAccountType, **values) -> BusinessAccountType:
        for key, value in values.items():
            if value is not None:
                setattr(item, key, value)
        self.db.flush()
        return item

    def create_benchmark_group(self, *, name: str, description: str | None, owner_employee_id: str | None, enabled: bool, metadata: dict) -> BenchmarkGroup:
        group = BenchmarkGroup(name=name, description=description, owner_employee_id=owner_employee_id, enabled=enabled, metadata_json=metadata)
        self.db.add(group)
        self.db.flush()
        return group

    def list_benchmark_groups(self) -> list[BenchmarkGroup]:
        return list(self.db.scalars(select(BenchmarkGroup).order_by(BenchmarkGroup.created_at.desc())))

    def update_benchmark_group(self, group: BenchmarkGroup, **values) -> BenchmarkGroup:
        metadata = values.pop("metadata", None)
        for key, value in values.items():
            if value is not None:
                setattr(group, key, value)
        if metadata is not None:
            group.metadata_json = metadata
        self.db.flush()
        return group

    def delete_benchmark_group(self, group: BenchmarkGroup) -> None:
        self.db.execute(delete(BenchmarkGroupMember).where(BenchmarkGroupMember.benchmark_group_id == group.id))
        self.db.execute(delete(BusinessAccountTypeBenchmarkGroup).where(BusinessAccountTypeBenchmarkGroup.benchmark_group_id == group.id))
        self.db.delete(group)
        self.db.flush()

    def add_benchmark_member(
        self,
        *,
        benchmark_group_id: str,
        creator_monitor_id: str | None,
        platform: str,
        creator_platform_id: str | None,
        creator_profile_url: str | None,
        display_name: str | None,
        platform_context: dict,
        enabled: bool,
    ) -> BenchmarkGroupMember:
        member = BenchmarkGroupMember(
            benchmark_group_id=benchmark_group_id,
            creator_monitor_id=creator_monitor_id,
            platform=platform,
            creator_platform_id=creator_platform_id,
            creator_profile_url=creator_profile_url,
            display_name=display_name,
            platform_context_json=platform_context,
            enabled=enabled,
        )
        self.db.add(member)
        self.db.flush()
        return member

    def list_benchmark_members(self, benchmark_group_id: str) -> list[BenchmarkGroupMember]:
        stmt = select(BenchmarkGroupMember).where(BenchmarkGroupMember.benchmark_group_id == benchmark_group_id)
        return list(self.db.scalars(stmt.order_by(BenchmarkGroupMember.created_at.desc())))

    def delete_benchmark_member(self, member: BenchmarkGroupMember) -> None:
        self.db.delete(member)
        self.db.flush()

    def bind_business_type_to_benchmark_group(self, *, business_account_type_id: str, benchmark_group_id: str) -> BusinessAccountTypeBenchmarkGroup:
        existing = self.db.scalar(
            select(BusinessAccountTypeBenchmarkGroup).where(
                BusinessAccountTypeBenchmarkGroup.business_account_type_id == business_account_type_id,
                BusinessAccountTypeBenchmarkGroup.benchmark_group_id == benchmark_group_id,
            )
        )
        if existing:
            return existing
        binding = BusinessAccountTypeBenchmarkGroup(business_account_type_id=business_account_type_id, benchmark_group_id=benchmark_group_id)
        self.db.add(binding)
        self.db.flush()
        return binding

    def list_business_types_for_benchmark_group(self, benchmark_group_id: str) -> list[tuple[BusinessAccountTypeBenchmarkGroup, BusinessAccountType | None]]:
        rows = self.db.execute(
            select(BusinessAccountTypeBenchmarkGroup, BusinessAccountType)
            .join(BusinessAccountType, BusinessAccountType.id == BusinessAccountTypeBenchmarkGroup.business_account_type_id, isouter=True)
            .where(BusinessAccountTypeBenchmarkGroup.benchmark_group_id == benchmark_group_id)
            .order_by(BusinessAccountTypeBenchmarkGroup.created_at.desc())
        )
        return list(rows)


    def create_task_template(self, *, name: str, template_type: str, platform: str | None, account_id: str | None, business_account_type_id: str | None, config: dict, enabled: bool) -> TaskTemplate:
        template = TaskTemplate(
            name=name,
            template_type=template_type,
            platform=platform,
            account_id=account_id,
            business_account_type_id=business_account_type_id,
            config_json=config,
            enabled=enabled,
        )
        self.db.add(template)
        self.db.flush()
        return template

    def list_task_templates(self) -> list[TaskTemplate]:
        return list(self.db.scalars(select(TaskTemplate).order_by(TaskTemplate.created_at.desc())))

    def update_task_template(self, template: TaskTemplate, *, name: str | None = None, enabled: bool | None = None, config: dict | None = None) -> TaskTemplate:
        if name is not None:
            template.name = name
        if enabled is not None:
            template.enabled = enabled
        if config is not None:
            template.config_json = config
        self.db.flush()
        return template

    def create_task_schedule(self, *, task_template_id: str, schedule_type: str, interval_seconds: int | None, daily_time_window: dict, enabled: bool, next_run_at) -> TaskSchedule:
        schedule = TaskSchedule(
            task_template_id=task_template_id,
            schedule_type=schedule_type,
            interval_seconds=interval_seconds,
            daily_time_window_json=daily_time_window,
            enabled=enabled,
            next_run_at=next_run_at,
        )
        self.db.add(schedule)
        self.db.flush()
        return schedule

    def list_task_schedules(self) -> list[TaskSchedule]:
        return list(self.db.scalars(select(TaskSchedule).order_by(TaskSchedule.created_at.desc())))

    def create_behavior_profile(self, *, name: str, description: str | None, enabled: bool, config: dict) -> BehaviorProfile:
        item = BehaviorProfile(name=name, description=description, enabled=enabled, config_json=config)
        self.db.add(item)
        self.db.flush()
        return item

    def list_behavior_profiles(self) -> list[BehaviorProfile]:
        return list(self.db.scalars(select(BehaviorProfile).order_by(BehaviorProfile.created_at.desc())))

    def create_network_egress_profile(self, *, name: str, strategy: str, description: str | None, enabled: bool, config: dict) -> NetworkEgressProfile:
        item = NetworkEgressProfile(name=name, strategy=strategy, description=description, enabled=enabled, config_json=config)
        self.db.add(item)
        self.db.flush()
        return item

    def list_network_egress_profiles(self) -> list[NetworkEgressProfile]:
        return list(self.db.scalars(select(NetworkEgressProfile).order_by(NetworkEgressProfile.created_at.desc())))

    def create_risk_policy(
        self,
        *,
        name: str,
        description: str | None,
        enabled: bool,
        behavior_profile_id: str | None,
        network_egress_profile_id: str | None,
        config: dict,
    ) -> RiskPolicy:
        item = RiskPolicy(
            name=name,
            description=description,
            enabled=enabled,
            behavior_profile_id=behavior_profile_id,
            network_egress_profile_id=network_egress_profile_id,
            config_json=config,
        )
        self.db.add(item)
        self.db.flush()
        return item

    def list_risk_policies(self) -> list[RiskPolicy]:
        return list(self.db.scalars(select(RiskPolicy).order_by(RiskPolicy.created_at.desc())))

    def bind_rule_set_to_business_type(self, *, business_account_type_id: str, rule_set_id: str, is_default: bool) -> BusinessAccountTypeRuleSet:
        existing = self.db.scalar(
            select(BusinessAccountTypeRuleSet).where(
                BusinessAccountTypeRuleSet.business_account_type_id == business_account_type_id,
                BusinessAccountTypeRuleSet.rule_set_id == rule_set_id,
            )
        )
        if existing:
            existing.is_default = is_default
            self.db.flush()
            return existing
        binding = BusinessAccountTypeRuleSet(business_account_type_id=business_account_type_id, rule_set_id=rule_set_id, is_default=is_default)
        self.db.add(binding)
        self.db.flush()
        return binding

    def list_rule_sets_for_business_type(self, business_account_type_id: str) -> list[tuple[BusinessAccountTypeRuleSet, KeywordRuleSet | None]]:
        rows = self.db.execute(
            select(BusinessAccountTypeRuleSet, KeywordRuleSet)
            .join(KeywordRuleSet, KeywordRuleSet.id == BusinessAccountTypeRuleSet.rule_set_id, isouter=True)
            .where(BusinessAccountTypeRuleSet.business_account_type_id == business_account_type_id)
            .order_by(BusinessAccountTypeRuleSet.created_at.desc())
        )
        return list(rows)

    def business_type_relation_counts(self, business_account_type_id: str) -> tuple[int, int]:
        rule_count = len(self.list_rule_sets_for_business_type(business_account_type_id))
        group_count = len(
            list(
                self.db.scalars(
                    select(BusinessAccountTypeBenchmarkGroup).where(
                        BusinessAccountTypeBenchmarkGroup.business_account_type_id == business_account_type_id
                    )
                )
            )
        )
        return rule_count, group_count

    def business_type_account_count(self, business_account_type_id: str) -> int:
        return self.db.scalar(
            select(func.count(PlatformAccount.id)).where(PlatformAccount.business_account_type_id == business_account_type_id)
        ) or 0

    def delete_business_account_type(self, item: BusinessAccountType) -> None:
        self.db.delete(item)
        self.db.flush()

    def list_keyword_rule_sets(self) -> list[KeywordRuleSet]:
        return list(self.db.scalars(select(KeywordRuleSet).order_by(KeywordRuleSet.created_at.desc())))

    def create_keyword_rule_set(
        self,
        *,
        name: str,
        rule_scope: str,
        enabled: bool,
        config: dict,
        created_by_user_id: str | None = None,
        created_by_employee_id: str | None = None,
    ) -> KeywordRuleSet:
        row = KeywordRuleSet(
            name=name,
            rule_scope=rule_scope,
            enabled=enabled,
            config_json=config,
            created_by_user_id=created_by_user_id,
            created_by_employee_id=created_by_employee_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def update_keyword_rule_set(self, row: KeywordRuleSet, **values) -> KeywordRuleSet:
        config = values.pop("config", None)
        for key, value in values.items():
            if value is not None:
                setattr(row, key, value)
        if config is not None:
            row.config_json = config
        self.db.flush()
        return row

    def delete_keyword_rule_set(self, row: KeywordRuleSet) -> None:
        self.db.execute(delete(KeywordRule).where(KeywordRule.rule_set_id == row.id))
        self.db.execute(delete(BusinessAccountTypeRuleSet).where(BusinessAccountTypeRuleSet.rule_set_id == row.id))
        self.db.delete(row)
        self.db.flush()

    def list_keyword_rules(self, rule_set_id: str) -> list[KeywordRule]:
        return list(self.db.scalars(select(KeywordRule).where(KeywordRule.rule_set_id == rule_set_id).order_by(KeywordRule.created_at.desc())))

    def create_keyword_rule(self, *, rule_set_id: str, keyword: str, normalized_keyword: str | None, match_mode: str, enabled: bool, weight: int) -> KeywordRule:
        row = KeywordRule(rule_set_id=rule_set_id, keyword=keyword, normalized_keyword=normalized_keyword, match_mode=match_mode, enabled=enabled, weight=weight)
        self.db.add(row)
        self.db.flush()
        return row

    def update_keyword_rule(self, row: KeywordRule, **values) -> KeywordRule:
        for key, value in values.items():
            if value is not None:
                setattr(row, key, value)
        self.db.flush()
        return row

    def delete_keyword_rule(self, row: KeywordRule) -> None:
        self.db.delete(row)
        self.db.flush()
