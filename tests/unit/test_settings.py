from packages.domain.settings import Settings


def test_database_url_accepts_cloud_provider_variable() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://gitseek:secret@database.example/gitseek?sslmode=require",
    )

    assert settings.database_url == (
        "postgresql+psycopg://gitseek:secret@database.example/gitseek?sslmode=require"
    )


def test_database_url_preserves_explicit_psycopg_driver() -> None:
    url = "postgresql+psycopg://gitseek:secret@database.example/gitseek"

    settings = Settings(_env_file=None, OPENSCOUT_DATABASE_URL=url)

    assert settings.database_url == url
