"""POST /api/apps/:appId/entities/:entityName/import — import entities from CSV."""

from __future__ import annotations

import os
import tempfile

from fastapi import Depends, File, UploadFile

from app.config import Settings
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_settings
from app.modules.entities import services

MAX_PARSE_ATTEMPTS = 3


async def import_entities(
    app_id: str,
    entity_name: str,
    file: UploadFile = File(...),
    ctx: AuthedContext = Depends(get_authed_context),
    settings: Settings = Depends(get_settings),
):
    raw = await file.read()
    return await services.import_entities(app_id, entity_name, raw, ctx, settings)


class _DuckDBEncodingError(Exception):
    pass


class _DuckDBParseError(Exception):
    pass


def _first_other_field(row: dict, exclude: str) -> str:
    for k in row:
        if k != exclude:
            return k
    return ""


def _parse_csv_duckdb(raw_bytes: bytes, schema: dict) -> list[dict]:
    import duckdb

    properties = schema.get("properties", {})
    field_names = list(properties.keys())

    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw_bytes)

        last_error: Exception | None = None
        for attempt in range(MAX_PARSE_ATTEMPTS):
            try:
                con = duckdb.connect()
                try:
                    if attempt == 0:
                        result = con.execute(
                            f"SELECT * FROM read_csv_auto('{tmp_path}')"
                        )
                    elif attempt == 1:
                        cols = ", ".join(
                            f"column{i} AS {name}" for i, name in enumerate(field_names)
                        ) if field_names else "*"
                        result = con.execute(
                            f"SELECT {cols} FROM read_csv_auto('{tmp_path}', "
                            f"header=false)"
                        )
                    else:
                        result = con.execute(
                            f"SELECT * FROM read_csv_auto('{tmp_path}', "
                            f"delim=',', header=true, ignore_errors=true)"
                        )

                    columns = [desc[0] for desc in result.description]
                    db_rows = result.fetchall()

                    records = []
                    for db_row in db_rows:
                        record = {}
                        for i, col in enumerate(columns):
                            val = db_row[i]
                            if val is None:
                                record[col] = ""
                            else:
                                record[col] = str(val)
                        _apply_title_defaults(record, properties)
                        records.append(record)

                    if records:
                        return records
                    last_error = Exception("UNABLE_TO_MAP")

                finally:
                    con.close()

            except duckdb.InvalidInputException as e:
                err_msg = str(e)
                if "unicode" in err_msg.lower() or "utf" in err_msg.lower():
                    raise _DuckDBEncodingError(err_msg)
                last_error = e
            except Exception as e:
                last_error = e

        raise _DuckDBParseError(last_error or "UNABLE_TO_MAP")

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _apply_title_defaults(record: dict, properties: dict):
    if "title" not in properties:
        return
    if "title" not in record:
        record["title"] = "UNKNOWN TITLE"
    elif record.get("title", "").strip() == "":
        record["title"] = "Untitled"
