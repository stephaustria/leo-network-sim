from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://sim:sim@localhost:5432/netsim"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()