from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AdminAuditLogOut(BaseModel):
    id: int
    actor_user_id: int | None = None
    actor_scope: str
    action: str
    target_type: str
    target_id: int | None = None
    client_ip: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    details_json: dict | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
