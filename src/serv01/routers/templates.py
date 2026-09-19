from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from serv01.dependencies import CurrentUser, DbSession
from serv01.models import DataTemplate
from serv01.schemas import TemplateCreate, TemplateResponse, TemplateUpdate

router = APIRouter(prefix="/api/templates", tags=["templates"])


def get_owned_template(session: DbSession, user: CurrentUser, template_id: UUID) -> DataTemplate:
    template = session.scalar(
        select(DataTemplate).where(
            DataTemplate.id == str(template_id), DataTemplate.owner_id == user.id
        )
    )
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template


@router.get("", response_model=list[TemplateResponse])
def list_templates(session: DbSession, user: CurrentUser) -> list[DataTemplate]:
    return list(
        session.scalars(
            select(DataTemplate)
            .where(DataTemplate.owner_id == user.id)
            .order_by(DataTemplate.created_at.desc())
        )
    )


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(payload: TemplateCreate, session: DbSession, user: CurrentUser) -> DataTemplate:
    template = DataTemplate(owner_id=user.id, **payload.model_dump(mode="json"))
    session.add(template)
    session.commit()
    return template


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(template_id: UUID, session: DbSession, user: CurrentUser) -> DataTemplate:
    return get_owned_template(session, user, template_id)


@router.patch("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: UUID,
    payload: TemplateUpdate,
    session: DbSession,
    user: CurrentUser,
) -> DataTemplate:
    template = get_owned_template(session, user, template_id)
    for field, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(template, field, value)
    session.commit()
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: UUID, session: DbSession, user: CurrentUser) -> Response:
    template = get_owned_template(session, user, template_id)
    session.delete(template)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
