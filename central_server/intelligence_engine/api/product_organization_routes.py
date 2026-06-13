from intelligence_engine.api.product_common import *


router = APIRouter(prefix="/api")


@router.post("/product/bootstrap-default-roles", response_model=list[RoleRead])
def bootstrap_default_roles(db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    repo = ProductRepository(db)
    roles = repo.ensure_default_roles()
    db.commit()
    return [RoleRead(id=role.id, name=role.name, description=role.description) for role in roles]


@router.post("/users", response_model=UserRead)
def create_user(request: UserCreateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    repo = ProductRepository(db)
    if repo.get_user_by_username(request.username):
        raise HTTPException(status_code=409, detail="username already exists")
    user = repo.create_user(
        username=request.username,
        display_name=request.display_name,
        email=request.email,
        password_hash=hash_password(request.password),
        role_names=[_enum_value(role) for role in request.role_names],
        metadata=request.metadata,
    )
    db.commit()
    return _user_read(repo, user)


@router.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    repo = ProductRepository(db)
    return [_user_read(repo, user) for user in repo.list_users()]


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    request: UserUpdateRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = ProductRepository(db)
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    repo.update_user(
        user,
        display_name=request.display_name,
        email=request.email,
        status=request.status,
        role_names=[_enum_value(role) for role in request.role_names] if request.role_names is not None else None,
    )
    db.commit()
    return _user_read(repo, user)


@router.post("/users/{user_id}/reset-password", response_model=UserRead)
def reset_user_password(
    user_id: str,
    request: UserPasswordResetRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = ProductRepository(db)
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    repo.set_password(user, hash_password(request.password))
    db.commit()
    return _user_read(repo, user)


@router.post("/employees", response_model=EmployeeRead)
def create_employee(request: EmployeeCreateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    employee = ProductRepository(db).create_employee(user_id=request.user_id, display_name=request.display_name, email=request.email, status=request.status)
    db.commit()
    return EmployeeRead(id=employee.id, user_id=employee.user_id, display_name=employee.display_name, email=employee.email, status=employee.status)


@router.post("/employees/with-user", response_model=EmployeeListItem)
def create_employee_with_user(
    request: EmployeeWithUserCreateRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = ProductRepository(db)
    if repo.get_user_by_username(request.username):
        raise HTTPException(status_code=409, detail="username already exists")
    user, employee = repo.create_employee_with_user(
        username=request.username,
        display_name=request.display_name,
        email=request.email,
        password_hash=hash_password(request.password),
        role_name=_enum_value(request.role),
    )
    db.commit()
    return _employee_list_item(repo, employee, repo.employee_account_counts(), repo.employee_agent_counts())


@router.get("/employees", response_model=list[EmployeeListItem])
def list_employees(db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    repo = ProductRepository(db)
    account_counts = repo.employee_account_counts()
    agent_counts = repo.employee_agent_counts()
    return [_employee_list_item(repo, employee, account_counts, agent_counts) for employee in repo.list_employees()]


@router.patch("/employees/{employee_id}", response_model=EmployeeListItem)
def update_employee(
    employee_id: str,
    request: EmployeeUpdateRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = ProductRepository(db)
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="employee not found")
    if request.display_name is not None:
        employee.display_name = request.display_name
    if request.email is not None:
        employee.email = request.email
    if request.status is not None:
        employee.status = request.status
    if request.user_id is not None:
        employee.user_id = request.user_id
    db.flush()
    db.commit()
    return _employee_list_item(repo, employee, repo.employee_account_counts(), repo.employee_agent_counts())
