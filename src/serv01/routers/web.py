from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jwt import InvalidTokenError
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from serv01.dependencies import DbSession
from serv01.domain import TaskRunStatus
from serv01.models import AutomationTask, DataTemplate, TaskLog, TaskRun, User
from serv01.routers.auth import token_for_user
from serv01.routers.tasks import clone_task, delete_task, pause_task, start_task, stop_task
from serv01.schemas import TaskCreate, TemplateCreate, UserCreate
from serv01.security import decode_access_token, hash_password, verify_password
from serv01.services import add_task_log, get_owned_task

router = APIRouter(tags=["web"], include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def authenticated_user(request: Request, session: DbSession) -> User | None:
    token = request.cookies.get("serv01_access_token")
    if token is None:
        return None
    try:
        payload = decode_access_token(token, request.app.state.settings.jwt_secret)
    except InvalidTokenError:
        return None
    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        return None
    user = session.get(User, user_id)
    return user if user is not None and user.is_active else None


def login_redirect() -> RedirectResponse:
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


def owned_web_task(session: DbSession, user: User, task_id: UUID) -> AutomationTask:
    task = get_owned_task(session, user, str(task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def web_login(
    request: Request,
    session: DbSession,
    email: str = Form(),
    password: str = Form(),
) -> Response:
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(password, user.password_hash) or not user.is_active:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Неверная почта или пароль"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    token_for_user(request, response, user)
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "register.html", {"error": None})


@router.post("/register")
def web_register(
    request: Request,
    session: DbSession,
    email: str = Form(),
    password: str = Form(),
    full_name: str = Form(),
) -> Response:
    try:
        payload = UserCreate(email=email, password=password, full_name=full_name)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": str(exc.errors()[0]["msg"])},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    user = User(
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Аккаунт с такой почтой уже существует"},
            status_code=status.HTTP_409_CONFLICT,
        )
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    token_for_user(request, response, user)
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("serv01_access_token")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, session: DbSession) -> Response:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    task_count = (
        session.scalar(
            select(func.count())
            .select_from(AutomationTask)
            .where(AutomationTask.owner_id == user.id)
        )
        or 0
    )
    successful_runs = (
        session.scalar(
            select(func.count())
            .select_from(TaskRun)
            .join(AutomationTask)
            .where(
                AutomationTask.owner_id == user.id,
                TaskRun.status == TaskRunStatus.SUCCESS.value,
            )
        )
        or 0
    )
    failed_runs = (
        session.scalar(
            select(func.count())
            .select_from(TaskRun)
            .join(AutomationTask)
            .where(
                AutomationTask.owner_id == user.id,
                TaskRun.status == TaskRunStatus.FAILED.value,
            )
        )
        or 0
    )
    logs = list(
        session.scalars(
            select(TaskLog)
            .join(AutomationTask)
            .where(AutomationTask.owner_id == user.id)
            .order_by(TaskLog.created_at.desc())
            .limit(10)
        )
    )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "task_count": task_count,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "logs": logs,
        },
    )


@router.get("/tasks", response_class=HTMLResponse)
def web_tasks(request: Request, session: DbSession) -> Response:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    tasks = list(
        session.scalars(
            select(AutomationTask)
            .where(AutomationTask.owner_id == user.id)
            .order_by(AutomationTask.created_at.desc())
        )
    )
    return templates.TemplateResponse(request, "tasks.html", {"user": user, "tasks": tasks})


@router.get("/tasks/new", response_class=HTMLResponse)
def new_task_page(request: Request, session: DbSession) -> Response:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    user_templates = list(
        session.scalars(select(DataTemplate).where(DataTemplate.owner_id == user.id))
    )
    return templates.TemplateResponse(
        request,
        "task_form.html",
        {"user": user, "templates": user_templates, "error": None},
    )


@router.post("/tasks/new")
def create_web_task(
    request: Request,
    session: DbSession,
    name: str = Form(),
    urls: str = Form(),
    template_id: str = Form(default=""),
    respect_robots_txt: str | None = Form(default=None),
) -> Response:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    user_templates = list(
        session.scalars(select(DataTemplate).where(DataTemplate.owner_id == user.id))
    )
    try:
        parsed_template_id = UUID(template_id) if template_id else None
        if parsed_template_id is not None and not any(
            item.id == str(parsed_template_id) for item in user_templates
        ):
            raise ValueError("Шаблон не найден")
        payload = TaskCreate(
            name=name,
            keywords=[name],
            urls=urls.splitlines(),
            template_id=parsed_template_id,
            respect_robots_txt=respect_robots_txt is not None,
        )
    except (ValidationError, ValueError) as exc:
        return templates.TemplateResponse(
            request,
            "task_form.html",
            {"user": user, "templates": user_templates, "error": str(exc)},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    task = AutomationTask(owner_id=user.id, **payload.model_dump(mode="json"))
    session.add(task)
    session.flush()
    add_task_log(session, task, "task.created", "Task created from web interface")
    session.commit()
    return RedirectResponse(f"/tasks/{task.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(task_id: UUID, request: Request, session: DbSession) -> Response:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    task = owned_web_task(session, user, task_id)
    runs = list(
        session.scalars(
            select(TaskRun).where(TaskRun.task_id == task.id).order_by(TaskRun.created_at.desc())
        )
    )
    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {"user": user, "task": task, "runs": runs},
    )


@router.post("/tasks/{task_id}/start")
def web_start_task(task_id: UUID, request: Request, session: DbSession) -> RedirectResponse:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    start_task(task_id, request, session, user)
    return RedirectResponse(f"/tasks/{task_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tasks/{task_id}/pause")
def web_pause_task(task_id: UUID, request: Request, session: DbSession) -> RedirectResponse:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    pause_task(task_id, request, session, user)
    return RedirectResponse(f"/tasks/{task_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tasks/{task_id}/stop")
def web_stop_task(task_id: UUID, request: Request, session: DbSession) -> RedirectResponse:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    stop_task(task_id, request, session, user)
    return RedirectResponse(f"/tasks/{task_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tasks/{task_id}/clone")
def web_clone_task(task_id: UUID, request: Request, session: DbSession) -> RedirectResponse:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    clone = clone_task(task_id, session, user)
    return RedirectResponse(f"/tasks/{clone.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tasks/{task_id}/delete")
def web_delete_task(task_id: UUID, request: Request, session: DbSession) -> RedirectResponse:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    delete_task(task_id, session, user)
    return RedirectResponse("/tasks", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/templates", response_class=HTMLResponse)
def web_templates(request: Request, session: DbSession) -> Response:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    user_templates = list(
        session.scalars(
            select(DataTemplate)
            .where(DataTemplate.owner_id == user.id)
            .order_by(DataTemplate.created_at.desc())
        )
    )
    return templates.TemplateResponse(
        request, "templates.html", {"user": user, "templates": user_templates}
    )


@router.get("/templates/new", response_class=HTMLResponse)
def new_template_page(request: Request, session: DbSession) -> Response:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    return templates.TemplateResponse(request, "template_form.html", {"user": user, "error": None})


@router.post("/templates/new")
def create_web_template(
    request: Request,
    session: DbSession,
    name: str = Form(),
    full_name: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    city: str = Form(default=""),
    comment: str = Form(default=""),
) -> Response:
    user = authenticated_user(request, session)
    if user is None:
        return login_redirect()
    try:
        payload = TemplateCreate(
            name=name,
            full_name=full_name or None,
            email=email or None,
            phone=phone or None,
            city=city or None,
            comment=comment or None,
        )
    except ValidationError as exc:
        return templates.TemplateResponse(
            request,
            "template_form.html",
            {"user": user, "error": str(exc)},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    session.add(DataTemplate(owner_id=user.id, **payload.model_dump(mode="json")))
    session.commit()
    return RedirectResponse("/templates", status_code=status.HTTP_303_SEE_OTHER)
