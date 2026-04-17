from app.routers.auth import router as auth_router
from app.routers.project import router as project_router
from app.routers.chapter import router as chapter_router
from app.routers.character import router as character_router
from app.routers.worldbuilding import router as worldbuilding_router
from app.routers.outline import router as outline_router
from app.routers.ai import router as ai_router
from app.routers.ai_config import router as ai_config_router
from app.routers.ai_batch import router as ai_batch_router
from app.routers.export import router as export_router
from app.routers.reference import router as reference_router
from app.routers.search import router as search_router
from app.routers.knowledge import router as knowledge_router
from app.routers.wizard import router as wizard_router
from app.routers.event import router as event_router
from app.routers.note import router as note_router
from app.routers.admin import router as admin_router
from app.routers.drama import router as drama_router
from app.routers.expansion import router as expansion_router

__all__ = [
    "auth_router",
    "project_router",
    "chapter_router",
    "character_router",
    "worldbuilding_router",
    "outline_router",
    "ai_router",
    "ai_config_router",
    "ai_batch_router",
    "export_router",
    "reference_router",
    "search_router",
    "knowledge_router",
    "wizard_router",
    "event_router",
    "note_router",
    "admin_router",
    "drama_router",
    "expansion_router",
]