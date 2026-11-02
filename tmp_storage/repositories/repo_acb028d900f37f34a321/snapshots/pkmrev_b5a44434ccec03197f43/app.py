from dataclasses import dataclass


@dataclass
class User:
    name: str


def load_user(name: str) -> User:
    return User(name=name)


def get_user(name: str) -> User:
    return load_user(name)
