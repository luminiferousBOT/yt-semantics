"""Entrypoint intended for a daily platform cron job."""
from app.database import Base, SessionLocal, engine
from app.ingestion import ingest_channel
from app.models import Channel


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for channel in db.query(Channel).all():
            result = ingest_channel(db, channel)
            print(f"{channel.name}: {result}")


if __name__ == "__main__":
    main()

