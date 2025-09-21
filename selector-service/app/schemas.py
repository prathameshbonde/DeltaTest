"""
Pydantic schemas for the selective test selector service API.

This module defines the request and response models for the /select-tests endpoint,
including all the nested data structures for changed files, dependency graphs,
and test selection results.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any


class Hunk(BaseModel):
    """Represents a contiguous range of changed lines in a file."""
    start: int
    end: int


class TouchedMethod(BaseModel):
    """Represents a method that was modified within the changed line ranges."""
    name: str
    signature: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    fqn: Optional[str] = None  # Fully qualified name like "com.foo.Bar#methodName"


class ChangedFile(BaseModel):
    """
    Represents a file that was modified in the change set.
    
    Includes enriched metadata for Java files such as package information,
    class names, and methods that were touched by the changes.
    """
    path: str
    change_type: str = Field(pattern=r"^[AMD]$")  # Added, Modified, Deleted
    hunks: List[Hunk] = Field(default_factory=list)
    file_name: Optional[str] = None
    lang: Optional[str] = None
    package: Optional[str] = None
    class_name: Optional[str] = None
    fully_qualified_class: Optional[str] = None
    touched_methods: List[TouchedMethod] = Field(default_factory=list)


class RepoInfo(BaseModel):
    """Repository information including name and commit references."""
    name: str
    base_commit: str
    head_commit: str


class Settings(BaseModel):
    """Configuration settings for test selection."""
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0)
    max_tests: int = 500


class SelectRequest(BaseModel):
    """
    Request payload for test selection.
    
    Contains all the information needed to analyze code changes and select
    appropriate tests: changed files, dependency graphs, call graphs, and settings.
    """
    repo: RepoInfo
    changed_files: List[ChangedFile] = Field(default_factory=list)
    jdeps_graph: Dict[str, List[str]] = Field(default_factory=dict)  # class -> [dependencies]
    call_graph: List[Dict[str, str]] = Field(default_factory=list)  # {caller, callee}
    allowed_tests: List[str] = Field(default_factory=list)  # Available tests in the project
    settings: Settings = Settings()


class SelectResponse(BaseModel):
    """
    Response payload with selected tests and analysis results.
    
    Includes the list of tests to run, human-readable explanations for the
    selections, a confidence score, and additional metadata about the analysis.
    """
    selected_tests: List[str]  # Test identifiers like "com.foo.BarTest#testMethod"
    explanations: Dict[str, str]  # Test ID -> explanation text
    confidence: float  # 0.0 to 1.0 indicating selection quality
    metadata: Dict[str, Any]  # Additional context like reason edges
