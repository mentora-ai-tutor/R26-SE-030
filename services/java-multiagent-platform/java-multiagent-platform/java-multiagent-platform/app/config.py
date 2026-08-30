import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "java_learning_db")
    JWT_SECRET: str = os.getenv(
        "USER_SERVICE_JWT_SECRET",
        os.getenv(
            "JWT_SECRET",
            os.getenv("JWT_SECRET_KEY", "change-me-in-production"),
        ),
    )
    JWT_ALGORITHM: str = os.getenv(
        "USER_SERVICE_JWT_ALGORITHM",
        os.getenv("JWT_ALGORITHM", "HS256"),
    )

settings = Settings()