"""Entities module — all entity CRUD endpoints."""

from fastapi import APIRouter, Depends

from app.modules.entities.count_entities import count_entities
from app.modules.entities.create_entity import create_entity
from app.modules.entities.delete_entity import delete_entity
from app.modules.entities.get_entity import get_entity
from app.modules.entities.helpers import known_entity
from app.modules.entities.list_entities import list_entities
from app.modules.entities.list_page import list_page
from app.modules.entities.update_entity import update_entity
from app.modules.entities.update_many import update_many
from app.modules.entities.user_me import get_me

router = APIRouter(prefix="/api/apps/{app_id}/entities", tags=["entities"])

router.add_api_route("/User/me", get_me, methods=["GET"])

router.add_api_route("/{entity_name}/update-many", update_many, methods=["PATCH"])

# The routes of @base44/sdk 0.8.49 — before `/{entity_name}/{id}`, which would
# read their last segment as a row's id. It does for every method they are
# not served on, and that is Base44's answer too: `GET …/aggregate` is "Entity
# Sale with ID aggregate not found", `POST …/count` is 405 (measured at the
# apps' host, 2026-09-29).
router.add_api_route("/{entity_name}/count", count_entities, methods=["GET"])
router.add_api_route("/{entity_name}/v2/list", list_page, methods=["GET"])

router.add_api_route("/{entity_name}", list_entities, methods=["GET"])
router.add_api_route("/{entity_name}", create_entity, methods=["POST"])

router.add_api_route("/{entity_name}/{id}", get_entity, methods=["GET"])
router.add_api_route("/{entity_name}/{id}", update_entity, methods=["PUT"])
router.add_api_route("/{entity_name}/{id}", delete_entity, methods=["DELETE"])
