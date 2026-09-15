# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple

from core.observation import BoundingBox, VisionElement, VisionObservation
from core.vision import VisionService, get_vision_service


class TargetResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    NOT_FOUND = "NOT_FOUND"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    AMBIGUOUS = "AMBIGUOUS"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    STALE_OBSERVATION = "STALE_OBSERVATION"


@dataclass
class ResolvedTarget:
    name: str
    bbox: BoundingBox
    confidence: float
    source: str  # "deterministic_window", "ocr", "vision_model", "explicit_coordinate"
    target_type: str = "element"  # "button", "input", "checkbox", "window", "coordinate", "element"
    status: TargetResolutionStatus = TargetResolutionStatus.RESOLVED
    ambiguous_candidates: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.status == TargetResolutionStatus.RESOLVED

    @property
    def center(self) -> Tuple[int, int]:
        return self.bbox.center

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "bbox": self.bbox.to_list(),
            "center": list(self.center),
            "confidence": self.confidence,
            "source": self.source,
            "target_type": self.target_type,
            "status": self.status.value,
            "ambiguous_candidates": self.ambiguous_candidates,
            "error": self.error,
        }


class TargetResolver:
    """
    Centralized Target Resolver for GUI elements in Jarvis.
    Enforces strict resolution hierarchy:
      1. Deterministic window / control info
      2. OCR text & bounding boxes
      3. Vision models
      4. Explicit coordinates
    """

    CONFIRM_SYNONYMS = ("ok", "ano", "yes", "potvrdit", "ulozit", "uložit", "submit", "pokracovat", "pokračovat", "save")
    CANCEL_SYNONYMS = ("zrusit", "zrušit", "cancel", "no", "ne", "storno", "zavrit", "zavřít", "close", "abort")

    def __init__(
        self,
        vision_service: Optional[VisionService] = None,
        confidence_threshold: float = 0.70,
        max_observation_age: float = 5.0,
    ) -> None:
        self.vision_service = vision_service or get_vision_service()
        self.confidence_threshold = confidence_threshold
        self.max_observation_age = max_observation_age

    @staticmethod
    def fuzzy_match(query: str, text: str) -> float:
        q = query.lower().strip()
        t = text.lower().strip()
        if not q or not t:
            return 0.0
        if q == t:
            return 1.0
        if q in t:
            return 0.95
        if t in q:
            return 0.90
        return SequenceMatcher(None, q, t).ratio()

    @staticmethod
    def parse_semantic_query(query: str) -> Tuple[str, Optional[str]]:
        """
        Parses phrases like 'tlačítko Přihlásit' -> ('Přihlásit', 'button')
        or 'pole Uživatelské jméno' -> ('Uživatelské jméno', 'input').
        """
        q = query.strip()
        type_prefixes = [
            (r"^(?:tlacitko|tlačítko|tl\.|button)\s+(.+)$", "button"),
            (r"^(?:pole|vstup|vstupni pole|input|textbox)\s+(.+)$", "input"),
            (r"^(?:checkbox|zaskrtavaci policko|zaškrtávací políčko)\s+(.+)$", "checkbox"),
            (r"^(?:zalozka|záložka|tab)\s+(.+)$", "tab"),
            (r"^(?:odkaz|link)\s+(.+)$", "link"),
            (r"^(?:ikona|icon)\s+(.+)$", "icon"),
            (r"^(?:okno|window)\s+(.+)$", "window"),
        ]
        for pattern, elem_type in type_prefixes:
            m = re.match(pattern, q, re.IGNORECASE)
            if m:
                return m.group(1).strip(), elem_type
        return q, None

    def resolve(
        self,
        target_query: Any,
        observation: Optional[VisionObservation] = None,
        expected_type: Optional[str] = None,
        force_fresh_observation: bool = False,
    ) -> ResolvedTarget:
        """
        Resolves a target query into a concrete ResolvedTarget with bounding box,
        confidence, and bounds validation.
        Enforces strict resolution hierarchy:
          1. Deterministic window / control
          2. OCR text & bounding boxes
          3. Local vision model
          4. Explicit coordinates fallback
        """
        query_str = str(target_query).strip()

        # Step 0: Observation staleness validation
        if observation is not None and not force_fresh_observation:
            if observation.is_stale(self.max_observation_age):
                return ResolvedTarget(
                    name=query_str,
                    bbox=BoundingBox(0, 0, 0, 0),
                    confidence=0.0,
                    source="stale_check",
                    target_type="element",
                    status=TargetResolutionStatus.STALE_OBSERVATION,
                    error=f"Observation is stale (age > {self.max_observation_age:.1f}s) and cannot be used safely.",
                )
            obs = observation
        else:
            obs = self.vision_service.capture_observation(force_fresh=True)

        clean_text, parsed_type = self.parse_semantic_query(query_str)
        target_type = expected_type or parsed_type or "element"

        # Priority 1: Deterministic window match
        det_window = self._check_deterministic_window(clean_text, obs)
        if det_window is not None:
            return det_window

        # Priority 2: OCR element matching
        ocr_target = self._resolve_ocr_target(clean_text, target_type, obs)
        if ocr_target is not None:
            return ocr_target

        # Priority 3: Local vision model (if installed and available)
        vision_target = self._check_vision_model(clean_text, target_type, obs)
        if vision_target is not None:
            return vision_target

        # Priority 4: Explicit coordinate fallback
        coord_target = self._check_coordinate_target(target_query, obs)
        if coord_target is not None:
            return coord_target

        # Target Not Found
        return ResolvedTarget(
            name=query_str,
            bbox=BoundingBox(0, 0, 0, 0),
            confidence=0.0,
            source="none",
            target_type=target_type,
            status=TargetResolutionStatus.NOT_FOUND,
            error=f"Target '{query_str}' could not be resolved in the current GUI state.",
        )

    def _check_vision_model(
        self,
        query: str,
        target_type: str,
        observation: VisionObservation,
    ) -> Optional[ResolvedTarget]:
        """Optionally resolve complex targets using local vision model if available."""
        if not observation.screenshot_path:
            return None
        try:
            from core.vision import VisionModelStatus
            from pathlib import Path
            if self.vision_service.vision.get_status() == VisionModelStatus.VISION_AVAILABLE:
                status, analysis = self.vision_service.vision.analyze(
                    Path(observation.screenshot_path),
                    f"Find the coordinates [x, y] of UI element matching '{query}'.",
                )
                if status == VisionModelStatus.VISION_AVAILABLE and analysis:
                    m = re.search(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]", analysis)
                    if m:
                        x, y = int(m.group(1)), int(m.group(2))
                        sw = observation.screen_width
                        sh = observation.screen_height
                        bbox = BoundingBox(x=x, y=y, width=10, height=10)
                        if 0 <= x < sw and 0 <= y < sh:
                            return ResolvedTarget(
                                name=query,
                                bbox=bbox,
                                confidence=0.80,
                                source="vision_model",
                                target_type=target_type,
                                status=TargetResolutionStatus.RESOLVED,
                            )
        except Exception:
            pass
        return None

    def _check_coordinate_target(
        self,
        target_query: Any,
        observation: Optional[VisionObservation],
    ) -> Optional[ResolvedTarget]:
        """Detect if target is an explicit coordinate query like '500,300' or {'x': 500, 'y': 300}."""
        x, y = None, None
        if isinstance(target_query, dict) and "x" in target_query and "y" in target_query:
            x = int(target_query["x"])
            y = int(target_query["y"])
        elif isinstance(target_query, (list, tuple)) and len(target_query) == 2:
            x = int(target_query[0])
            y = int(target_query[1])
        elif isinstance(target_query, str):
            m = re.match(r"^\s*(\d+)\s*[,;\s]\s*(\d+)\s*$", target_query)
            if m:
                x = int(m.group(1))
                y = int(m.group(2))

        if x is not None and y is not None:
            sw = observation.screen_width if observation else 1920
            sh = observation.screen_height if observation else 1080
            bbox = BoundingBox(x=x, y=y, width=1, height=1)

            if 0 <= x < sw and 0 <= y < sh:
                return ResolvedTarget(
                    name=f"[{x},{y}]",
                    bbox=bbox,
                    confidence=1.0,
                    source="explicit_coordinate",
                    target_type="coordinate",
                    status=TargetResolutionStatus.RESOLVED,
                )
            else:
                return ResolvedTarget(
                    name=f"[{x},{y}]",
                    bbox=bbox,
                    confidence=1.0,
                    source="explicit_coordinate",
                    target_type="coordinate",
                    status=TargetResolutionStatus.OUT_OF_BOUNDS,
                    error=f"Coordinates [{x}, {y}] are out of screen bounds [{sw}x{sh}].",
                )
        return None

    def _check_deterministic_window(
        self,
        query: str,
        observation: VisionObservation,
    ) -> Optional[ResolvedTarget]:
        """Checks if the query matches the active window title deterministically."""
        norm_query = query.lower()
        active_title = observation.window_title or ""
        if norm_query and active_title and (norm_query in active_title.lower() or active_title.lower() in norm_query):
            return ResolvedTarget(
                name=active_title,
                bbox=BoundingBox(0, 0, observation.screen_width, observation.screen_height),
                confidence=1.0,
                source="deterministic_window",
                target_type="window",
                status=TargetResolutionStatus.RESOLVED,
            )
        return None

    def _resolve_ocr_target(
        self,
        query: str,
        target_type: str,
        observation: VisionObservation,
    ) -> Optional[ResolvedTarget]:
        """Resolves target against OCR elements with confidence scoring and ambiguity detection."""
        if not observation.elements:
            return None

        q_lower = query.lower()
        candidates: List[Tuple[float, VisionElement]] = []

        # Check for dialog confirm/cancel keywords
        is_confirm_query = q_lower in ("potvrdit", "ok", "confirm", "submit", "ulozit")
        is_cancel_query = q_lower in ("zrusit", "zrušit", "cancel", "storno", "close")

        for el in observation.elements:
            score = 0.0
            el_text_lower = el.text.lower()

            if is_confirm_query and any(w == el_text_lower or (w in el_text_lower and len(el_text_lower) < len(w) + 4) for w in self.CONFIRM_SYNONYMS):
                score = 1.0 if el_text_lower in self.CONFIRM_SYNONYMS else 0.85
            elif is_cancel_query and any(w == el_text_lower or (w in el_text_lower and len(el_text_lower) < len(w) + 4) for w in self.CANCEL_SYNONYMS):
                score = 1.0 if el_text_lower in self.CANCEL_SYNONYMS else 0.85
            else:
                score = self.fuzzy_match(query, el.text)

            if score >= 0.5:
                # Weight by OCR confidence
                combined_score = score * (0.5 + 0.5 * el.confidence)
                candidates.append((combined_score, el))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[0], reverse=True)
        best_score, best_el = candidates[0]

        # Check for ambiguity (competing candidates with score delta < 0.05)
        ambiguous = []
        for s, el in candidates[1:]:
            if abs(s - best_score) < 0.05:
                ambiguous.append(el.text)

        # Bounds validation
        sw = observation.screen_width
        sh = observation.screen_height
        if not best_el.bbox.is_inside(sw, sh):
            return ResolvedTarget(
                name=best_el.text,
                bbox=best_el.bbox,
                confidence=best_el.confidence,
                source=best_el.source,
                target_type=target_type,
                status=TargetResolutionStatus.OUT_OF_BOUNDS,
                error=f"Bounding box {best_el.bbox.to_list()} is outside screen bounds [{sw}x{sh}].",
            )

        # Ambiguity status
        if ambiguous:
            return ResolvedTarget(
                name=best_el.text,
                bbox=best_el.bbox,
                confidence=best_el.confidence,
                source=best_el.source,
                target_type=target_type,
                status=TargetResolutionStatus.AMBIGUOUS,
                ambiguous_candidates=[best_el.text] + ambiguous,
                error=f"Multiple ambiguous elements match '{query}': {[best_el.text] + ambiguous}",
            )

        # Low confidence check
        if best_el.confidence < self.confidence_threshold:
            return ResolvedTarget(
                name=best_el.text,
                bbox=best_el.bbox,
                confidence=best_el.confidence,
                source=best_el.source,
                target_type=target_type,
                status=TargetResolutionStatus.LOW_CONFIDENCE,
                error=f"Element '{best_el.text}' matched with low confidence {best_el.confidence:.2f} (threshold {self.confidence_threshold:.2f}).",
            )

        return ResolvedTarget(
            name=best_el.text,
            bbox=best_el.bbox,
            confidence=best_el.confidence,
            source=best_el.source,
            target_type=target_type,
            status=TargetResolutionStatus.RESOLVED,
        )


# Global default instance
_default_target_resolver: Optional[TargetResolver] = None


def get_target_resolver() -> TargetResolver:
    global _default_target_resolver
    if _default_target_resolver is None:
        _default_target_resolver = TargetResolver()
    return _default_target_resolver
