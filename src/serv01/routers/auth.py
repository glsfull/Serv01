from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from serv01.dependencies import CurrentUser, DbSession
from serv01.models import User
from serv01.schemas import LoginRequest, TokenResponse, UserCreate, UserResponse
from serv01.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def token_for_user(request: Request, user: User) -> TokenResponse:
    settings = request.app.state.settings
    return TokenResponse(
        access_token=create_access_token(
            user.id,
            settings.jwt_secret,
            settings.access_token_minutes,
        )
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request, session: DbSession) -> TokenResponse:
    user = User(
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    return token_for_user(request, user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, session: DbSession) -> TokenResponse:
    user = session.scalar(select(User).where(User.email == str(payload.email)))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return token_for_user(request, user)


@router.get("/me", response_model=UserResponse)
def current_user(user: CurrentUser) -> User:
    return user
