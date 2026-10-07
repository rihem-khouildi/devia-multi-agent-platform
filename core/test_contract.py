"""
Test Contract — structured test cases derived from User Story acceptance criteria.

Produced by ImplementationAdvisor, consumed by DeveloperAgent (test generation)
and TesterAgent (validation/repair).

Rules enforced here:
- repository layer is ONLY generated when the story explicitly requests it.
- DTO validation uses Jakarta Validator, never assertThrows on constructors.
- Controller tests require a real HTTP endpoint in the analysis.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Valid target layers and what they mean
VALID_LAYERS = ("dto", "validation", "service", "controller", "repository")


@dataclass
class TestCase:
    """A single test case describing expected behavior for one unit."""

    id: str
    title: str
    target_class: str          # e.g. AuthenticationRequest, AuthenticationController
    target_layer: str          # dto | validation | service | controller | repository
    scenario: str              # Short human-readable scenario
    given: str = ""
    when: str = ""
    then: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    expected_result: Dict[str, Any] = field(default_factory=dict)
    expected_status: Optional[int] = None   # HTTP status code for controller tests
    validation_expected: bool = False        # True → expects Jakarta ConstraintViolation
    should_generate: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "target_class": self.target_class,
            "target_layer": self.target_layer,
            "scenario": self.scenario,
            "given": self.given,
            "when": self.when,
            "then": self.then,
            "input_data": self.input_data,
            "expected_result": self.expected_result,
            "expected_status": self.expected_status,
            "validation_expected": self.validation_expected,
            "should_generate": self.should_generate,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        layer = str(data.get("target_layer", "service")).lower()
        if layer not in VALID_LAYERS:
            layer = "service"
        return cls(
            id=str(data.get("id", "TC0")),
            title=str(data.get("title", "")),
            target_class=str(data.get("target_class", "")),
            target_layer=layer,
            scenario=str(data.get("scenario", "")),
            given=str(data.get("given", "")),
            when=str(data.get("when", "")),
            then=str(data.get("then", "")),
            input_data=dict(data.get("input_data") or {}),
            expected_result=dict(data.get("expected_result") or {}),
            expected_status=data.get("expected_status"),
            validation_expected=bool(data.get("validation_expected", False)),
            should_generate=bool(data.get("should_generate", True)),
        )


@dataclass
class TestContract:
    """Ordered collection of test cases for a single User Story."""

    story_id: str
    test_cases: List[TestCase] = field(default_factory=list)

    # ── Read-only helpers ─────────────────────────────────────────────

    @property
    def active_cases(self) -> List[TestCase]:
        return [tc for tc in self.test_cases if tc.should_generate]

    def cases_for_layer(self, layer: str) -> List[TestCase]:
        return [tc for tc in self.active_cases if tc.target_layer == layer]

    def cases_for_class(self, class_name: str) -> List[TestCase]:
        return [tc for tc in self.active_cases if tc.target_class == class_name]

    def has_repository_tests(self) -> bool:
        return any(tc.target_layer == "repository" for tc in self.active_cases)

    def target_classes(self) -> List[str]:
        seen: List[str] = []
        for tc in self.active_cases:
            if tc.target_class and tc.target_class not in seen:
                seen.append(tc.target_class)
        return seen

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "story_id": self.story_id,
            "test_cases": [tc.to_dict() for tc in self.test_cases],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestContract":
        return cls(
            story_id=str(data.get("story_id", "")),
            test_cases=[TestCase.from_dict(tc) for tc in data.get("test_cases", [])],
        )

    @classmethod
    def empty(cls, story_id: str) -> "TestContract":
        return cls(story_id=story_id, test_cases=[])

    # ── LLM helpers ───────────────────────────────────────────────────

    def to_prompt_snippet(self) -> str:
        """Return a compact LLM-friendly summary of the test contract."""
        cases = self.active_cases
        if not cases:
            return "No test cases defined."
        lines = [f"Test Contract — {len(cases)} case(s) to implement:"]
        for tc in cases:
            layer_hint = ""
            if tc.target_layer == "validation":
                layer_hint = " [use Jakarta Validator, NOT assertThrows on constructor]"
            elif tc.target_layer == "controller":
                status = f" → HTTP {tc.expected_status}" if tc.expected_status else ""
                layer_hint = f" [WebMvcTest{status}]"
            elif tc.target_layer == "service":
                layer_hint = " [Mockito mock dependencies]"
            elif tc.target_layer == "repository":
                layer_hint = " [only if explicitly required by story]"
            lines.append(
                f"  [{tc.id}] {tc.title}"
                f" | class={tc.target_class} | layer={tc.target_layer}{layer_hint}"
            )
            if tc.given:
                lines.append(f"         Given: {tc.given}")
            if tc.then:
                lines.append(f"         Then:  {tc.then}")
        return "\n".join(lines)
