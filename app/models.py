from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel, UniqueConstraint

MIN_GROUP_SIZE = 2
MAX_GROUP_SIZE = 4


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AttendanceStatus(str, Enum):
    SEARCHING = "searching"
    GROUPED = "grouped"


# --- Utilisateurs -----------------------------------------------------------

class UserBase(SQLModel):
    name: str = Field(min_length=1, max_length=50)
    age: int | None = Field(default=None, ge=18, le=120)
    city: str | None = None
    bio: str | None = Field(default=None, max_length=500)
    # Genres séparés par des virgules, ex. "rock,electro"
    genres: str = ""


class User(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class UserCreate(UserBase):
    pass


class UserPublic(UserBase):
    id: int


# --- Concerts ---------------------------------------------------------------

class ConcertBase(SQLModel):
    artist: str = Field(min_length=1)
    venue: str
    city: str
    date: datetime


class Concert(ConcertBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class ConcertCreate(ConcertBase):
    pass


class ConcertPublic(ConcertBase):
    id: int


# --- Participation : "je vais à ce concert et je cherche un groupe de n" -----

class Attendance(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "concert_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    concert_id: int = Field(foreign_key="concert.id", index=True)
    # Taille totale du groupe voulu, en se comptant soi-même
    group_size: int = Field(ge=MIN_GROUP_SIZE, le=MAX_GROUP_SIZE)
    status: AttendanceStatus = AttendanceStatus.SEARCHING
    group_id: int | None = Field(default=None, foreign_key="group.id")


class AttendanceCreate(SQLModel):
    user_id: int
    group_size: int = Field(ge=MIN_GROUP_SIZE, le=MAX_GROUP_SIZE)


# --- Swipes -----------------------------------------------------------------

class Swipe(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("swiper_id", "target_id", "concert_id"),)

    id: int | None = Field(default=None, primary_key=True)
    swiper_id: int = Field(foreign_key="user.id", index=True)
    target_id: int = Field(foreign_key="user.id", index=True)
    concert_id: int = Field(foreign_key="concert.id", index=True)
    liked: bool
    created_at: datetime = Field(default_factory=utcnow)


class SwipeCreate(SQLModel):
    swiper_id: int
    target_id: int
    liked: bool


# --- Groupes ----------------------------------------------------------------

class Group(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    concert_id: int = Field(foreign_key="concert.id", index=True)
    size: int
    created_at: datetime = Field(default_factory=utcnow)


class GroupMember(SQLModel, table=True):
    group_id: int = Field(foreign_key="group.id", primary_key=True)
    user_id: int = Field(foreign_key="user.id", primary_key=True)


class GroupPublic(SQLModel):
    id: int
    concert: ConcertPublic
    members: list[UserPublic]
    created_at: datetime


class SwipeResult(SQLModel):
    mutual: bool
    group: GroupPublic | None = None


# --- Messages du groupe -----------------------------------------------------

class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    user_id: int = Field(foreign_key="user.id")
    content: str = Field(min_length=1, max_length=2000)
    created_at: datetime = Field(default_factory=utcnow)


class MessageCreate(SQLModel):
    user_id: int
    content: str = Field(min_length=1, max_length=2000)
