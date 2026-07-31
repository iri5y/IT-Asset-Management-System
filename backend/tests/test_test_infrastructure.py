from sqlalchemy import text


def test_sqlite_fixture_enables_foreign_key_enforcement(db_session):
    enabled = db_session.execute(text("PRAGMA foreign_keys")).scalar_one()

    assert enabled == 1
