from app import get_user


def user_route(name: str) -> dict[str, str]:
    user = get_user(name)
    return {"name": user.name}
