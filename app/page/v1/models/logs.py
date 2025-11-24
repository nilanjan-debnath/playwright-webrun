from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime


class NetworkLog(BaseModel):
    """
    Represents a single captured network or console event.
    """

    type: Literal["console", "request", "response"] = Field(
        ..., description="The type of log event."
    )
    timestamp: datetime = Field(default_factory=datetime.now)

    # For console
    message: Optional[str] = Field(None, description="Console message content.")

    # For request
    url: Optional[str] = Field(None, description="Request or Response URL.")
    method: Optional[str] = Field(None, description="Request method (GET, POST, etc.).")
    resourceType: Optional[str] = Field(
        None, description="Type of resource (xhr, fetch, document, etc.)."
    )

    # For response
    status: Optional[int] = Field(None, description="Response HTTP status code.")

    # Common
    headers: Optional[dict] = Field(None, description="HTTP headers.")
    body: Optional[str] = Field(None, description="HTTP body content (if captured).")


class DebugResponse(BaseModel):
    """
    The structured response for the network debug endpoint.
    """

    page_title: str = Field(..., description="The final title of the page.")
    final_url: str = Field(..., description="The final URL after any redirects.")
    total_logs: int = Field(..., description="Total number of log events captured.")
    logs: List[NetworkLog] = Field(
        ..., description="A list of all captured network and console events."
    )
