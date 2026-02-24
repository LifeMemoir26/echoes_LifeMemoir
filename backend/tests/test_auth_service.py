import pytest

from src.application.auth.service import AuthService


class FakeDB:
    def __init__(self):
        self.users = {}

    def username_exists(self, username: str) -> bool:
        return username in self.users

    def create_user(self, username: str, password_hash: str) -> None:
        self.users[username] = {"password_hash": password_hash}

    def get_user_by_username(self, username: str):
        return self.users.get(username)

    def update_last_login(self, username: str) -> None:
        self.users[username]["last_login"] = True


def test_register_success():
    svc = AuthService(db=FakeDB())
    username = svc.register("alice", "password123")
    assert username == "alice"


def test_register_duplicate():
    db = FakeDB()
    svc = AuthService(db=db)
    svc.register("alice", "password123")

    with pytest.raises(ValueError, match="USERNAME_TAKEN"):
        svc.register("alice", "password123")


def test_register_invalid_username_rejected():
    svc = AuthService(db=FakeDB())

    with pytest.raises(ValueError, match="INVALID_USERNAME"):
        svc.register("alice!", "password123")


def test_login_invalid_credentials_rejected():
    db = FakeDB()
    svc = AuthService(db=db)
    svc.register("alice", "password123")

    with pytest.raises(ValueError, match="INVALID_CREDENTIALS"):
        svc.login("alice", "wrong-password")
