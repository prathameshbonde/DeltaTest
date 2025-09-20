from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any


class Hunk(BaseModel):
    start: int
    end: int

class TouchedMethod(BaseModel):
    name: str
    signature: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    fqn: Optional[str] = None


class ChangedFile(BaseModel):
    path: str
    change_type: str = Field(pattern=r"^[AMD]$")
    hunks: List[Hunk] = Field(default_factory=list)
    file_name: Optional[str] = None
    lang: Optional[str] = None
    package: Optional[str] = None
    class_name: Optional[str] = None
    fully_qualified_class: Optional[str] = None
    touched_methods: List[TouchedMethod] = Field(default_factory=list)


class RepoInfo(BaseModel):
    name: str
    base_commit: str
    head_commit: str


class Settings(BaseModel):
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0)
    max_tests: int = 500


class SelectRequest(BaseModel):
    repo: RepoInfo
    changed_files: List[ChangedFile] = Field(default_factory=list)
    jdeps_graph: Dict[str, List[str]] = Field(default_factory=dict)
    call_graph: List[Dict[str, str]] = Field(default_factory=list)  # {caller, callee}
    allowed_tests: List[str] = Field(default_factory=list)
    settings: Settings = Settings()


class SelectResponse(BaseModel):
    selected_tests: List[str]
    explanations: Dict[str, str]
    confidence: float
    metadata: Dict[str, Any]
