from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from typing import Optional

from app.core.config import settings

security = HTTPBearer()


class TokenPayload(BaseModel):
    id: str
    student_id: str
    role: str
    iat: int
    exp: int

    @property
    def db_student_id(self) -> str:
        """The ID stored in the peer-learning students collection.
        Falls back to student_id if id is a MongoDB ObjectId format."""
        return self.id


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=["HS256"],
        )
        user_id: Optional[str] = payload.get("id")
        student_id: Optional[str] = payload.get("student_id")
        role: Optional[str] = payload.get("role")
        iat: Optional[int] = payload.get("iat")
        exp: Optional[int] = payload.get("exp")

        if user_id is None or student_id is None or role is None:
            raise credentials_exception

        return TokenPayload(
            id=user_id,
            student_id=student_id,
            role=role,
            iat=iat or 0,
            exp=exp or 0,
        )
    except JWTError:
        raise credentials_exception
