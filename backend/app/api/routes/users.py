from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.routes.auth import serialize_user
from app.core.security import hash_password, require_permission
from app.db.session import get_db
from app.models import AccessProfile, AuditLog, Collaborator, User, UserAccessProfile
from app.schemas import UserCreate, UserOut, UserUpdate
from app.services.audit_log import record_audit_log, snapshot
from app.services.regional import effective_managed_regionals, normalize_regional

router = APIRouter(prefix="/users", tags=["users"])
ALLOWED_ROLES = {"viewer", "operator", "admin", "collaborator", "regional_manager_viewer", "base_manager", "workspace_restricted"}


def _resolve_collaborator_link(db: Session, collaborator_id: int | None, current_user_id: int | None) -> Collaborator | None:
    """Valida um `collaborator_id` recebido em create/update de usuário: precisa existir e não
    pode já estar vinculado a outro usuário (vínculo é 1-para-1, ver models.py User.collaborator_id).
    """
    if collaborator_id is None:
        return None
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    existing = db.scalar(select(User).where(User.collaborator_id == collaborator_id))
    if existing and existing.id != current_user_id:
        raise HTTPException(status_code=409, detail=f"Este colaborador já está vinculado ao usuário {existing.email}.")
    return collaborator


def _set_user_profiles(db: Session, user: User, profile_ids: list[int] | None) -> None:
    if profile_ids is None:
        return
    unique_ids = sorted({int(profile_id) for profile_id in profile_ids})
    profiles = db.scalars(select(AccessProfile).where(AccessProfile.id.in_(unique_ids))).all() if unique_ids else []
    found_ids = {profile.id for profile in profiles}
    missing = [profile_id for profile_id in unique_ids if profile_id not in found_ids]
    if missing:
        raise HTTPException(status_code=422, detail=f"Perfil de acesso inválido: {missing[0]}.")
    inactive = next((profile for profile in profiles if not profile.active), None)
    if inactive:
        raise HTTPException(status_code=422, detail="Perfil inativo não pode ser vinculado a um usuário.")
    db.query(UserAccessProfile).filter(UserAccessProfile.user_id == user.id).delete(synchronize_session=False)
    for profile_id in unique_ids:
        db.add(UserAccessProfile(user_id=user.id, profile_id=profile_id))
    if not unique_ids:
        # A remoção do último perfil é uma revogação real. Sem este marcador,
        # o role legado (ex.: operator) ainda concederia permissões.
        user.role = "workspace_restricted"
    elif len(unique_ids) == 1:
        profile = profiles[0]
        if profile.legacy_role:
            user.role = profile.legacy_role


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(require_permission("users:manage"))):
    return [serialize_user(item) for item in db.scalars(select(User).order_by(User.name.asc())).all()]


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("users:manage"))):
    if payload.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=422, detail="Perfil inválido.")
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email já cadastrado.")
    _resolve_collaborator_link(db, payload.collaborator_id, current_user_id=None)
    managed_regionals = effective_managed_regionals(payload.managed_regional, payload.managed_regionals)
    item = User(
        name=payload.name,
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        active=payload.active,
        collaborator_id=payload.collaborator_id,
        managed_regional=None,
        managed_regionals=managed_regionals,
    )
    db.add(item)
    db.flush()
    _set_user_profiles(db, item, payload.access_profile_ids)
    record_audit_log(db, user, "create", "users", item.id, None, snapshot(item))
    db.commit()
    db.refresh(item)
    return serialize_user(item)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users:manage")),
):
    item = db.get(User, user_id)
    if not item:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    before = snapshot(item)
    updates = payload.model_dump(exclude_unset=True)
    if "role" in updates and updates["role"] not in ALLOWED_ROLES:
        raise HTTPException(status_code=422, detail="Perfil inválido.")
    if "email" in updates and updates["email"]:
        email = str(updates["email"]).strip().lower()
        exists = db.scalar(select(User).where(User.email == email).where(User.id != user_id))
        if exists:
            raise HTTPException(status_code=409, detail="Email já cadastrado.")
        item.email = email
    if "password" in updates and updates["password"]:
        item.password_hash = hash_password(str(updates["password"]))
    if "collaborator_id" in updates:
        _resolve_collaborator_link(db, updates["collaborator_id"], current_user_id=item.id)
        item.collaborator_id = updates["collaborator_id"]
    if "managed_regional" in updates or "managed_regionals" in updates:
        item.managed_regionals = effective_managed_regionals(updates.get("managed_regional"), updates.get("managed_regionals"))
        item.managed_regional = None
    for field in ("name", "role", "active"):
        if field in updates and updates[field] is not None:
            setattr(item, field, updates[field])
    if "access_profile_ids" in updates:
        _set_user_profiles(db, item, updates["access_profile_ids"])
    record_audit_log(db, user, "update", "users", item.id, before, snapshot(item))
    db.commit()
    db.refresh(item)
    return serialize_user(item)


@router.delete("/{user_id}", response_model=UserOut)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users:manage")),
):
    item = db.get(User, user_id)
    if not item:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if item.id == user.id:
        raise HTTPException(status_code=400, detail="Não é possível excluir o próprio usuário logado.")
    before = snapshot(item)
    response = serialize_user(item)
    record_audit_log(db, user, "delete", "users", item.id, before, None)
    db.execute(update(AuditLog).where(AuditLog.user_id == item.id).values(user_id=None))
    db.delete(item)
    db.commit()
    return response
