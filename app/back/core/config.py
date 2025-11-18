# app/back/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 세션/보안용 키 (운영환경에서는 .env 로 관리 추천)
    SECRET_KEY: str = "change-this-secret-in-env"

    # 환경
    ENV: str = "local"
    DEBUG: bool = True

    # ★ Neon DB URL (.env 에서 읽어올 값)
    DATABASE_URL: str

    # pydantic-settings v2 스타일 설정
    model_config = SettingsConfigDict(
        env_file=".env",           # 프로젝트 루트에 .env 두면 자동 로드
        env_file_encoding="utf-8",
        extra="ignore",            # .env 에 다른 값 있어도 무시 (에러 X)
    )
    
    # NCP SENS (SMS)
    NCP_SENS_ACCESS_KEY: str = ""
    NCP_SENS_SECRET_KEY: str = ""
    NCP_SENS_SERVICE_ID: str = "ncp:sms:kr:362313047390:wecandoeat"
    NCP_SENS_CALLING_NUMBER: str = ""  # 발신번호 (예: 01012345678)


settings = Settings()
