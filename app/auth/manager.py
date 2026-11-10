import uuid

from fastapi_users import BaseUserManager, UUIDIDMixin

from app.config import get_settings
from app.models import User


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    def __init__(self, user_db):
        super().__init__(user_db)
        settings = get_settings()
        self.reset_password_token_secret = settings.secret_key
        self.verification_token_secret = settings.secret_key
