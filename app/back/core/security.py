from passlib.context import CryptContext

# bcrypt 대신 pbkdf2_sha256 사용 (호환성 좋고 안전함)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    평문 비밀번호를 해시로 변환
    """
    # pbkdf2_sha256은 길이 제한 이슈 없음
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    입력한 비밀번호가 저장된 해시와 일치하는지 검증
    """
    return pwd_context.verify(plain_password, hashed_password)
