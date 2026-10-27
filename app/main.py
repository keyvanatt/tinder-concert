from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlmodel import Session, col, select

from app.db import get_session, init_db
from app.matching import build_mutual_graph, find_group
from app.models import (
    Attendance,
    AttendanceCreate,
    AttendanceStatus,
    Concert,
    ConcertCreate,
    ConcertPublic,
    Group,
    GroupMember,
    GroupPublic,
    Message,
    MessageCreate,
    Swipe,
    SwipeCreate,
    SwipeResult,
    User,
    UserCreate,
    UserPublic,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Tinder Concert", lifespan=lifespan)

SessionDep = Annotated[Session, Depends(get_session)]


def get_or_404(session: Session, model, obj_id: int):
    obj = session.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {obj_id} introuvable")
    return obj


def get_attendance(session: Session, user_id: int, concert_id: int) -> Attendance | None:
    return session.exec(
        select(Attendance).where(
            Attendance.user_id == user_id, Attendance.concert_id == concert_id
        )
    ).first()


def group_to_public(session: Session, group: Group) -> GroupPublic:
    members = session.exec(
        select(User)
        .join(GroupMember, col(GroupMember.user_id) == col(User.id))
        .where(GroupMember.group_id == group.id)
        .order_by(col(User.id))
    ).all()
    concert = session.get(Concert, group.concert_id)
    return GroupPublic(
        id=group.id,
        concert=ConcertPublic.model_validate(concert),
        members=[UserPublic.model_validate(m) for m in members],
        created_at=group.created_at,
    )


def genres_of(user: User) -> set[str]:
    return {g.strip().lower() for g in user.genres.split(",") if g.strip()}


# --- Utilisateurs -----------------------------------------------------------

@app.post("/users", response_model=UserPublic, status_code=201)
def create_user(data: UserCreate, session: SessionDep):
    user = User.model_validate(data)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@app.get("/users/{user_id}", response_model=UserPublic)
def read_user(user_id: int, session: SessionDep):
    return get_or_404(session, User, user_id)


@app.get("/users/{user_id}/groups", response_model=list[GroupPublic])
def read_user_groups(user_id: int, session: SessionDep):
    get_or_404(session, User, user_id)
    groups = session.exec(
        select(Group)
        .join(GroupMember, col(GroupMember.group_id) == col(Group.id))
        .where(GroupMember.user_id == user_id)
        .order_by(col(Group.created_at).desc())
    ).all()
    return [group_to_public(session, g) for g in groups]


# --- Concerts ---------------------------------------------------------------

@app.post("/concerts", response_model=ConcertPublic, status_code=201)
def create_concert(data: ConcertCreate, session: SessionDep):
    concert = Concert.model_validate(data)
    session.add(concert)
    session.commit()
    session.refresh(concert)
    return concert


@app.get("/concerts", response_model=list[ConcertPublic])
def list_concerts(session: SessionDep, city: str | None = None):
    query = select(Concert).order_by(col(Concert.date))
    if city:
        query = query.where(col(Concert.city).ilike(city))
    return session.exec(query).all()


@app.get("/concerts/{concert_id}", response_model=ConcertPublic)
def read_concert(concert_id: int, session: SessionDep):
    return get_or_404(session, Concert, concert_id)


@app.post("/concerts/{concert_id}/attend", response_model=Attendance, status_code=201)
def attend_concert(concert_id: int, data: AttendanceCreate, session: SessionDep):
    get_or_404(session, Concert, concert_id)
    get_or_404(session, User, data.user_id)
    if get_attendance(session, data.user_id, concert_id):
        raise HTTPException(409, "Déjà inscrit à ce concert")
    attendance = Attendance(
        user_id=data.user_id, concert_id=concert_id, group_size=data.group_size
    )
    session.add(attendance)
    session.commit()
    session.refresh(attendance)
    return attendance


@app.delete("/concerts/{concert_id}/attend/{user_id}", status_code=204)
def leave_concert(concert_id: int, user_id: int, session: SessionDep):
    attendance = get_attendance(session, user_id, concert_id)
    if attendance is None:
        raise HTTPException(404, "Pas inscrit à ce concert")
    if attendance.status == AttendanceStatus.GROUPED:
        raise HTTPException(409, "Déjà dans un groupe pour ce concert")
    session.delete(attendance)
    session.commit()


@app.get("/concerts/{concert_id}/feed", response_model=list[UserPublic])
def concert_feed(
    concert_id: int,
    user_id: int,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
):
    """Profils à swiper : mêmes concert et taille de groupe, pas encore swipés.

    Ceux qui nous ont déjà likés passent en premier (match plus probable),
    puis ceux avec le plus de genres musicaux en commun.
    """
    me = get_or_404(session, User, user_id)
    my_attendance = get_attendance(session, user_id, concert_id)
    if my_attendance is None:
        raise HTTPException(404, "Pas inscrit à ce concert")
    if my_attendance.status != AttendanceStatus.SEARCHING:
        return []

    already_swiped = select(Swipe.target_id).where(
        Swipe.swiper_id == user_id, Swipe.concert_id == concert_id
    )
    candidates = session.exec(
        select(User)
        .join(Attendance, col(Attendance.user_id) == col(User.id))
        .where(
            Attendance.concert_id == concert_id,
            Attendance.status == AttendanceStatus.SEARCHING,
            Attendance.group_size == my_attendance.group_size,
            User.id != user_id,
            col(User.id).not_in(already_swiped),
        )
    ).all()

    liked_me = set(
        session.exec(
            select(Swipe.swiper_id).where(
                Swipe.target_id == user_id,
                Swipe.concert_id == concert_id,
                col(Swipe.liked).is_(True),
            )
        ).all()
    )
    my_genres = genres_of(me)
    candidates = sorted(
        candidates,
        key=lambda u: (u.id not in liked_me, -len(my_genres & genres_of(u)), u.id),
    )
    return candidates[:limit]


@app.post("/concerts/{concert_id}/swipes", response_model=SwipeResult, status_code=201)
def swipe(concert_id: int, data: SwipeCreate, session: SessionDep):
    if data.swiper_id == data.target_id:
        raise HTTPException(400, "Impossible de se swiper soi-même")
    mine = get_attendance(session, data.swiper_id, concert_id)
    theirs = get_attendance(session, data.target_id, concert_id)
    if mine is None or theirs is None:
        raise HTTPException(404, "Les deux personnes doivent être inscrites au concert")
    if AttendanceStatus.GROUPED in (mine.status, theirs.status):
        raise HTTPException(409, "Une des deux personnes a déjà un groupe")
    if mine.group_size != theirs.group_size:
        raise HTTPException(409, "Tailles de groupe recherchées différentes")
    existing = session.exec(
        select(Swipe).where(
            Swipe.swiper_id == data.swiper_id,
            Swipe.target_id == data.target_id,
            Swipe.concert_id == concert_id,
        )
    ).first()
    if existing:
        raise HTTPException(409, "Déjà swipé")

    session.add(Swipe(concert_id=concert_id, **data.model_dump()))
    session.flush()

    if not data.liked:
        session.commit()
        return SwipeResult(mutual=False)

    reciprocal = session.exec(
        select(Swipe).where(
            Swipe.swiper_id == data.target_id,
            Swipe.target_id == data.swiper_id,
            Swipe.concert_id == concert_id,
            col(Swipe.liked).is_(True),
        )
    ).first()
    if reciprocal is None:
        session.commit()
        return SwipeResult(mutual=False)

    group = try_form_group(session, concert_id, mine.group_size, data.swiper_id, data.target_id)
    session.commit()
    if group is None:
        return SwipeResult(mutual=True)
    return SwipeResult(mutual=True, group=group_to_public(session, group))


def try_form_group(
    session: Session, concert_id: int, size: int, a: int, b: int
) -> Group | None:
    """Forme un groupe si une clique de `size` likes réciproques contient a et b."""
    pool = session.exec(
        select(Attendance).where(
            Attendance.concert_id == concert_id,
            Attendance.status == AttendanceStatus.SEARCHING,
            Attendance.group_size == size,
        )
    ).all()
    by_user = {att.user_id: att for att in pool}
    likes = {
        (s.swiper_id, s.target_id)
        for s in session.exec(
            select(Swipe).where(Swipe.concert_id == concert_id, col(Swipe.liked).is_(True))
        ).all()
        if s.swiper_id in by_user and s.target_id in by_user
    }
    members = find_group(build_mutual_graph(likes), a, b, size)
    if members is None:
        return None

    group = Group(concert_id=concert_id, size=size)
    session.add(group)
    session.flush()
    for user_id in members:
        session.add(GroupMember(group_id=group.id, user_id=user_id))
        att = by_user[user_id]
        att.status = AttendanceStatus.GROUPED
        att.group_id = group.id
        session.add(att)
    return group


# --- Groupes et messages ----------------------------------------------------

def check_member(session: Session, group_id: int, user_id: int) -> None:
    if session.get(GroupMember, (group_id, user_id)) is None:
        raise HTTPException(403, "Pas membre de ce groupe")


@app.get("/groups/{group_id}", response_model=GroupPublic)
def read_group(group_id: int, user_id: int, session: SessionDep):
    group = get_or_404(session, Group, group_id)
    check_member(session, group_id, user_id)
    return group_to_public(session, group)


@app.get("/groups/{group_id}/messages", response_model=list[Message])
def read_messages(group_id: int, user_id: int, session: SessionDep):
    get_or_404(session, Group, group_id)
    check_member(session, group_id, user_id)
    return session.exec(
        select(Message).where(Message.group_id == group_id).order_by(col(Message.id))
    ).all()


@app.post("/groups/{group_id}/messages", response_model=Message, status_code=201)
def post_message(group_id: int, data: MessageCreate, session: SessionDep):
    get_or_404(session, Group, group_id)
    check_member(session, group_id, data.user_id)
    message = Message(group_id=group_id, **data.model_dump())
    session.add(message)
    session.commit()
    session.refresh(message)
    return message
