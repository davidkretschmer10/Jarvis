from __future__ import annotations

from typing import Any, Dict
from difflib import SequenceMatcher

import requests

from tools.base import JSON, ToolContext


def _post_agent(ctx: ToolContext, action: str, value: Any = "") -> JSON:
    if ctx.dry_run:
        return {"ok": True, "dry_run": True, "action": action, "value": value}

    r = requests.post(
        f"{ctx.agent_base_url.rstrip('/')}/command",
        json={"action": action, "value": value},
        timeout=10,
    )
    try:
        data: Dict[str, Any] = r.json()
    except Exception:
        data = {"raw": r.text}
    agent_ok = data.get("ok", True) if isinstance(data, dict) else True
    return {"ok": bool(r.ok and agent_ok), "status_code": r.status_code, "data": data}


def _get_agent_health(ctx: ToolContext) -> JSON:
    if ctx.dry_run:
        return {"ok": True, "dry_run": True}

    r = requests.get(f"{ctx.agent_base_url.rstrip('/')}/health", timeout=5)
    try:
        data: Dict[str, Any] = r.json()
    except Exception:
        data = {"raw": r.text}
    return {"ok": r.ok, "status_code": r.status_code, "data": data}


def _agent_tool_result(result: JSON) -> JSON:
    return {"ok": bool(result.get("ok", False)), "result": result}

class AgentHealthTool:
    name = "agent_health"
    description = "Check that the local PC-control Agent is running."

class AgentHealthTool:
    name = "agent_health"
    description = "Check that the local PC-control Agent is running."
    input_schema: JSON = {"type": "object", "properties": {}}

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        return _get_agent_health(ctx)


class OpenAppTool:
    name = "open_app"
    description = "Open a Windows application by name via local Agent."
    input_schema: JSON = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        name = str(tool_input.get("name", ""))
        
        # Check if we have a pending approved path from confirmation
        if state and state.data.get("action_confirmed") and state.data.get("pending_app_path"):
            path = state.data.pop("pending_app_path")
            state.data.pop("pending_app_name", None)
            state.data.pop("pending_candidates", None)
            state.data["action_confirmed"] = False
            
            res = _post_agent(ctx, "open_path", path)
            if res.get("ok"):
                _post_agent(ctx, "learn_preference", {"query": name, "path": path})
            return _agent_tool_result(res)
            
        res = _post_agent(ctx, "open", name)
        
        if not res.get("ok") and isinstance(res.get("data"), dict) and res["data"].get("error") == "CONFIRMATION_REQUIRED":
            err_data = res["data"]
            if state:
                state.data["pending_app_path"] = err_data.get("pending_app_path")
                state.data["pending_app_name"] = err_data.get("pending_app_name")
                state.data["pending_candidates"] = err_data.get("pending_candidates", [])
            return {
                "ok": False,
                "error": "CONFIRMATION_REQUIRED",
                "message": err_data.get("message")
            }
            
        if res.get("ok") and isinstance(res.get("data"), dict):
            path = res["data"].get("path")
            if path:
                _post_agent(ctx, "learn_preference", {"query": name, "path": path})
                
        return _agent_tool_result(res)


class WriteTextTool:
    name = "write_text"
    description = "Write text on the screen using keyboard simulation."
    input_schema: JSON = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        text = str(tool_input.get("text", ""))
        return _agent_tool_result(_post_agent(ctx, "write", text))


class ClickTool:
    name = "click"
    description = "Perform a mouse click via local Agent, optionally at x/y screen coordinates."
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "button": {"type": "string"},
            "clicks": {"type": "integer"},
        },
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        payload: Any
        if "x" in tool_input and "y" in tool_input:
            payload = {
                "x": int(tool_input["x"]),
                "y": int(tool_input["y"]),
                "button": str(tool_input.get("button", "left")),
                "clicks": int(tool_input.get("clicks", 1)),
            }
        else:
            payload = ""
        return _agent_tool_result(_post_agent(ctx, "click", payload))


class OpenWebsiteTool:
    name = "open_website"
    description = "Open a URL in the default browser via local Agent."
    input_schema: JSON = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        url = str(tool_input.get("url", ""))
        return _agent_tool_result(_post_agent(ctx, "website", url))


class PressKeyTool:
    name = "press_key"
    description = "Press one keyboard key via local Agent."
    input_schema: JSON = {
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        return _agent_tool_result(_post_agent(ctx, "press", str(tool_input.get("key", ""))))


class HotkeyTool:
    name = "hotkey"
    description = "Press a keyboard shortcut via local Agent, for example ctrl+l."
    input_schema: JSON = {
        "type": "object",
        "properties": {"keys": {"type": "array", "items": {"type": "string"}}},
        "required": ["keys"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        keys = tool_input.get("keys", [])
        if not isinstance(keys, list):
            keys = [str(keys)]
        return _agent_tool_result(_post_agent(ctx, "hotkey", [str(key) for key in keys]))


class ScreenshotTool:
    name = "screenshot"
    description = "Take a screenshot via local Agent and save it to a screenshots folder."
    input_schema: JSON = {
        "type": "object",
        "properties": {"folder": {"type": "string"}},
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        payload = {"folder": str(tool_input.get("folder", "screenshots"))}
        result = _post_agent(ctx, "screenshot", payload)
        data = result.get("data", {})
        screenshot_path = None
        if isinstance(data, dict):
            raw_result = data.get("result")
            if isinstance(raw_result, dict):
                screenshot_path = raw_result.get("path")
        out: JSON = _agent_tool_result(result)
        if screenshot_path:
            out["created_files"] = [str(screenshot_path)]
            out["save_to_state"] = {"last_screenshot_path": str(screenshot_path)}
        return out


class ReadScreenTool:
    name = "read_screen"
    description = "Read visible screen text with OCR via local Agent."
    input_schema: JSON = {
        "type": "object",
        "properties": {"lang": {"type": "string"}},
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        payload = {"lang": str(tool_input.get("lang", "ces+eng"))}
        result = _post_agent(ctx, "read_screen", payload)
        data = result.get("data", {})
        text = ""
        if isinstance(data, dict):
            raw_result = data.get("result")
            if isinstance(raw_result, dict):
                text = str(raw_result.get("text", ""))
        out: JSON = _agent_tool_result(result)
        if text:
            out["save_to_state"] = {"last_screen_text": text}
        return out


class SmartClickTool:
    name = "smart_click"
    description = "Click on a button, menu item, link, or element matching the target text on screen."
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "target": {"type": "string"},
        },
        "required": ["target"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        target = str(tool_input.get("target", "")).strip()
        if not target:
            return {"ok": False, "error": "Chybi cilovy text pro kliknuti."}

        from vision.ui_detector import UIDetector
        detector = UIDetector()
        ui_response = detector.detect_screen()
        
        candidates = []
        for el in ui_response.elements:
            if el.type in ("button", "menu_item", "tab", "dropdown", "popup", "checkbox"):
                score = fuzzy_match(target, el.text)
                if score >= 0.5:
                    candidates.append((score, el))
        
        if not candidates:
            return {"ok": False, "error": f"Nenalezen zadny prvek odpovidajici '{target}'."}
            
        candidates.sort(key=lambda c: c[0], reverse=True)
        
        best_score, best_el = candidates[0]
        ambiguous = []
        for score, el in candidates[1:]:
            if abs(score - best_score) < 0.05:
                ambiguous.append(el)
                
        if ambiguous:
            options = [best_el.text] + [el.text for el in ambiguous]
            if not state.data.get("action_confirmed"):
                return {
                    "ok": False,
                    "error": "CONFIRMATION_REQUIRED",
                    "message": f"Nalezl jsem více prvků s podobným názvem: {', '.join(options)}. Přejete si přesto pokračovat s prvkem '{best_el.text}'?"
                }
            state.data["action_confirmed"] = False
            
        # Confidence score check
        confidence = best_el.confidence
        if confidence < 0.70:
            if not state.data.get("action_confirmed"):
                return {
                    "ok": False,
                    "error": "CONFIRMATION_REQUIRED",
                    "message": f"Nízká spolehlivost ({confidence:.2f}) pro prvek '{best_el.text}'. Přejete si přesto pokračovat?"
                }
            state.data["action_confirmed"] = False
        elif confidence < 0.90:
            import logging
            logging.getLogger(__name__).warning(f"Varování: Nízká spolehlivost ({confidence:.2f}) pro prvek '{best_el.text}'.")
            
        cx, cy = best_el.center
        
        sw = ui_response.image_width or 1920
        sh = ui_response.image_height or 1080
        if not (0 <= cx < sw and 0 <= cy < sh):
            return {"ok": False, "error": f"Souradnice [{cx}, {cy}] jsou mimo rozsah obrazovky [{sw}x{sh}]."}
            
        res = _post_agent(ctx, "click", {"x": cx, "y": cy})
        return {
            "ok": res.get("ok", False),
            "result": f"Kliknuto na prvek '{best_el.text}' ({best_el.type}) na [{cx}, {cy}].",
            "element": best_el.to_dict(),
        }


class SmartWriteTool:
    name = "smart_write"
    description = "Type text into an input field matching a target label."
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "target": {"type": "string"},
            "text": {"type": "string"},
        },
        "required": ["target", "text"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        target = str(tool_input.get("target", "")).strip()
        text = str(tool_input.get("text", ""))
        
        from vision.ui_detector import UIDetector
        detector = UIDetector()
        ui_response = detector.detect_screen()
        
        candidates = []
        for el in ui_response.elements:
            if el.type == "input":
                score = fuzzy_match(target, el.text)
                if score >= 0.5:
                    candidates.append((score, el))
        
        if not candidates:
            for el in ui_response.elements:
                score = fuzzy_match(target, el.text)
                if score >= 0.5:
                    best_input = None
                    min_dist = 999999
                    for inp in ui_response.elements:
                        if inp.type == "input":
                            dist = ((inp.x - el.x)**2 + (inp.y - el.y)**2)**0.5
                            if dist < min_dist:
                                min_dist = dist
                                best_input = inp
                    if best_input and min_dist < 150:
                        candidates.append((score * 0.9, best_input))
                        
        if not candidates:
            return {"ok": False, "error": f"Nenalezeno zadne vstupni pole odpovidajici '{target}'."}
            
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, best_el = candidates[0]
        
        # Confidence score check
        confidence = best_el.confidence
        if confidence < 0.70:
            if not state.data.get("action_confirmed"):
                return {
                    "ok": False,
                    "error": "CONFIRMATION_REQUIRED",
                    "message": f"Nízká spolehlivost ({confidence:.2f}) pro prvek '{best_el.text}'. Přejete si přesto pokračovat?"
                }
            state.data["action_confirmed"] = False
        elif confidence < 0.90:
            import logging
            logging.getLogger(__name__).warning(f"Varování: Nízká spolehlivost ({confidence:.2f}) pro prvek '{best_el.text}'.")
            
        cx, cy = best_el.center
        
        click_res = _post_agent(ctx, "click", {"x": cx, "y": cy})
        if not click_res.get("ok"):
            return {"ok": False, "error": "Nepodarilo se kliknout na vstupni pole."}
            
        write_res = _post_agent(ctx, "write", text)
        return {
            "ok": write_res.get("ok", False),
            "result": f"Napsano '{text}' do pole '{best_el.text}' na [{cx}, {cy}].",
            "element": best_el.to_dict(),
        }


class SmartCheckboxTool:
    name = "smart_checkbox"
    description = "Check or uncheck a checkbox matching a target label."
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "target": {"type": "string"},
            "checked": {"type": "boolean"},
        },
        "required": ["target", "checked"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        target = str(tool_input.get("target", "")).strip()
        
        from vision.ui_detector import UIDetector
        detector = UIDetector()
        ui_response = detector.detect_screen()
        
        candidates = []
        for el in ui_response.elements:
            if el.type == "checkbox":
                score = fuzzy_match(target, el.text)
                if score >= 0.5:
                    candidates.append((score, el))
                    
        if not candidates:
            return {"ok": False, "error": f"Nenalezen checkbox odpovidajici '{target}'."}
            
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, best_el = candidates[0]
        
        # Confidence score check
        confidence = best_el.confidence
        if confidence < 0.70:
            if not state.data.get("action_confirmed"):
                return {
                    "ok": False,
                    "error": "CONFIRMATION_REQUIRED",
                    "message": f"Nízká spolehlivost ({confidence:.2f}) pro prvek '{best_el.text}'. Přejete si přesto pokračovat?"
                }
            state.data["action_confirmed"] = False
        elif confidence < 0.90:
            import logging
            logging.getLogger(__name__).warning(f"Varování: Nízká spolehlivost ({confidence:.2f}) pro prvek '{best_el.text}'.")
            
        cx, cy = best_el.center
        res = _post_agent(ctx, "click", {"x": cx, "y": cy})
        return {
            "ok": res.get("ok", False),
            "result": f"Kliknuto na checkbox '{best_el.text}' na [{cx}, {cy}] pro zmenu stavu.",
            "element": best_el.to_dict(),
        }


class CloseWindowTool:
    name = "close_window"
    description = "Close the currently active window."
    input_schema: JSON = {"type": "object", "properties": {}}

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        if not state.data.get("action_confirmed"):
            return {
                "ok": False,
                "error": "CONFIRMATION_REQUIRED",
                "message": "Detekoval jsem rizikovou akci: zavření okna. Přejete si přesto pokračovat?"
            }
        state.data["action_confirmed"] = False
        res = _post_agent(ctx, "hotkey", ["alt", "f4"])
        return {
            "ok": res.get("ok", False),
            "result": "Odeslana klavesova zkratka Alt+F4 pro zavreni okna.",
        }


class ConfirmDialogTool:
    name = "confirm_dialog"
    description = "Confirm the currently active dialog window (e.g. click OK, Yes, Save, Potvrdit)."
    input_schema: JSON = {"type": "object", "properties": {}}

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        if not state.data.get("action_confirmed"):
            return {
                "ok": False,
                "error": "CONFIRMATION_REQUIRED",
                "message": "Detekoval jsem rizikovou akci: kliknutí na potvrzovací tlačítko dialogu. Přejete si přesto pokračovat?"
            }
        state.data["action_confirmed"] = False
        
        from vision.ui_detector import UIDetector
        detector = UIDetector()
        ui_response = detector.detect_screen()
        
        confirm_words = ("ok", "ano", "yes", "potvrdit", "ulozit", "uložit", "submit", "pokracovat", "pokračovat")
        candidates = []
        for el in ui_response.elements:
            if el.type == "button":
                text_lower = el.text.lower()
                for word in confirm_words:
                    if word == text_lower or (word in text_lower and len(text_lower) < len(word) + 4):
                        candidates.append((1.0 if word == text_lower else 0.8, el))
                        break
                        
        if not candidates:
            return {"ok": False, "error": "Nenalezeno zadne potvrzovaci tlacitko na obrazovce."}
            
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, best_el = candidates[0]
        cx, cy = best_el.center
        res = _post_agent(ctx, "click", {"x": cx, "y": cy})
        return {
            "ok": res.get("ok", False),
            "result": f"Kliknuto na potvrzovaci tlacitko '{best_el.text}' na [{cx}, {cy}].",
            "element": best_el.to_dict(),
        }


class CancelDialogTool:
    name = "cancel_dialog"
    description = "Cancel the currently active dialog window (e.g. click Cancel, No, Storno, Zrusit, Zavrit)."
    input_schema: JSON = {"type": "object", "properties": {}}

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        from vision.ui_detector import UIDetector
        detector = UIDetector()
        ui_response = detector.detect_screen()
        
        cancel_words = ("zrusit", "zrušit", "cancel", "no", "ne", "storno", "zavrit", "zavřít", "close")
        candidates = []
        for el in ui_response.elements:
            if el.type == "button":
                text_lower = el.text.lower()
                for word in cancel_words:
                    if word == text_lower or (word in text_lower and len(text_lower) < len(word) + 4):
                        candidates.append((1.0 if word == text_lower else 0.8, el))
                        break
                        
        if not candidates:
            return {"ok": False, "error": "Nenalezeno zadne tlacitko pro zruseni na obrazovce."}
            
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, best_el = candidates[0]
        cx, cy = best_el.center
        res = _post_agent(ctx, "click", {"x": cx, "y": cy})
        return {
            "ok": res.get("ok", False),
            "result": f"Kliknuto na storno tlacitko '{best_el.text}' na [{cx}, {cy}].",
            "element": best_el.to_dict(),
        }


class OpenSearchResultTool:
    name = "open_search_result"
    description = "Open the first search result on screen."
    input_schema: JSON = {"type": "object", "properties": {}}

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        from vision.ui_detector import UIDetector
        detector = UIDetector()
        ui_response = detector.detect_screen()
        
        candidates = []
        for el in ui_response.elements:
            if el.type in ("button", "menu_item") and el.y > 180:
                score = 0.5
                if len(el.text) > 10:
                    score += 0.3
                if el.x < 600:
                    score += 0.2
                candidates.append((score, el))
                
        if not candidates:
            return {"ok": False, "error": "Nenalezen zadny vysledek vyhledavani k otevreni."}
            
        candidates.sort(key=lambda c: (c[0], -c[1].y), reverse=True)
        _, best_el = candidates[0]
        cx, cy = best_el.center
        res = _post_agent(ctx, "click", {"x": cx, "y": cy})
        return {
            "ok": res.get("ok", False),
            "result": f"Otevren prvni vysledek vyhledavani: '{best_el.text}' na [{cx}, {cy}].",
            "element": best_el.to_dict(),
        }


def fuzzy_match(query: str, text: str) -> float:
    q = query.lower().strip()
    t = text.lower().strip()
    if q in t or t in q:
        return 1.0
    return SequenceMatcher(None, q, t).ratio()


class RefreshAppsTool:
    name = "refresh_apps"
    description = "Rebuild the applications cache and scan for installed apps."
    input_schema: JSON = {"type": "object", "properties": {}}

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        res = _post_agent(ctx, "refresh_apps")
        return _agent_tool_result(res)


