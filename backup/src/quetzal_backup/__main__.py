"""Entry point: python -m quetzal_backup."""

import logging

from quetzal_backup.catalog_backup import Settings, back_up, create_s3_client, today_in_guatemala


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    back_up(settings, create_s3_client(settings), today_in_guatemala())


if __name__ == "__main__":
    main()
