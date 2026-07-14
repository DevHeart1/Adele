"""
ADELE — Chrome DevTools Protocol Client
======================================
Provides lightweight CDP communication for element grounding and browser manipulation.
"""

import json
import httpx
import websockets
from typing import Dict, Any, List, Optional


class CDPClient:
    def __init__(self, ports: Optional[List[int]] = None):
        self.ports = ports or [9222, 9223, 9224, 9225, 9230]

    async def find_page_target(self) -> Optional[Dict[str, Any]]:
        """Probes remote debugging ports and returns the first page target with a WebSocket URL."""
        async with httpx.AsyncClient() as client:
            for port in self.ports:
                try:
                    response = await client.get(f"http://127.0.0.1:{port}/json", timeout=1.0)
                    if response.status_code == 200:
                        targets = response.json()
                        for target in targets:
                            # We only care about page targets that can accept debugging connections
                            if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                                target["port"] = port
                                return target
                except Exception:
                    continue
        return None

    async def evaluate_js(self, expression: str) -> Any:
        """Connects to the first active page target and evaluates a JavaScript expression."""
        target = await self.find_page_target()
        if not target:
            return None

        ws_url = target["webSocketDebuggerUrl"]
        try:
            async with websockets.connect(ws_url) as websocket:
                cmd = {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": True
                    }
                }
                await websocket.send(json.dumps(cmd))
                response_str = await websocket.recv()
                response = json.loads(response_str)

                result = response.get("result", {})
                if "exceptionDetails" in result:
                    # JS execution exception
                    return None

                return result.get("result", {}).get("value")
        except Exception:
            return None

    def _get_unified_js(self, query: str, action_type: str = "ground", action_value: str = "") -> str:
        """Constructs the unified Javascript matching and action execution script."""
        template = """
        (() => {
          const query = QUERY_PLACEHOLDER;
          const actionType = ACTION_TYPE_PLACEHOLDER;
          const actionValue = ACTION_VALUE_PLACEHOLDER;

          const normalize = (value) => String(value || "")
            .toLowerCase()
            .replace(/[\u2026]/g, "...")
            .replace(/[^\p{L}\p{N}]+/gu, " ")
            .trim();
          const queryNormalized = normalize(query);
          const queryWords = new Set(queryNormalized.split(/\s+/).filter(Boolean));
          const visible = (element, rect) => {
            const style = window.getComputedStyle(element);
            return rect.width > 2
              && rect.height > 2
              && style.visibility !== "hidden"
              && style.display !== "none"
              && Number(style.opacity || "1") > 0.02;
          };
          const textFor = (element) => [
            element.getAttribute("aria-label"),
            element.getAttribute("title"),
            element.getAttribute("alt"),
            element.getAttribute("placeholder"),
            element.innerText,
            element.textContent,
            element.value
          ].filter(Boolean).join(" ");
          const score = (text, element) => {
            const normalizedText = normalize(text);
            if (!normalizedText || !queryNormalized) return 0;
            if (normalizedText === queryNormalized) return 100;
            if (normalizedText.includes(queryNormalized)) return 82;
            if (queryNormalized.includes(normalizedText) && normalizedText.length >= 3) return 72;
            const textWords = new Set(normalizedText.split(/\s+/).filter(Boolean));
            let overlap = 0;
            for (const word of queryWords) {
              if (textWords.has(word)) overlap += 1;
            }
            let base = overlap > 0 ? 40 + overlap * 12 : 0;
            const role = String(element.getAttribute("role") || "").toLowerCase();
            const tag = element.tagName.toLowerCase();
            if (["button", "a", "input", "textarea", "select", "summary"].includes(tag)) base += 8;
            if (["button", "link", "menuitem", "tab", "textbox"].includes(role)) base += 8;
            return base;
          };
          const selectors = [
            "button", "a", "input", "textarea", "select", "summary",
            "[role='button']", "[role='link']", "[role='menuitem']",
            "[role='tab']", "[role='textbox']", "[aria-label]",
            "[title]", "[placeholder]", "[contenteditable='true']",
            "[tabindex]"
          ];
          const candidates = Array.from(new Set(document.querySelectorAll(selectors.join(","))));
          let best = null;
          let bestElement = null;
          for (const element of candidates) {
            const rect = element.getBoundingClientRect();
            if (!visible(element, rect)) continue;
            const labelText = textFor(element);
            const candidateScore = score(labelText, element);
            if (candidateScore <= 0) continue;
            if (!best || candidateScore > best.score) {
              const browserLeftBorder = Math.max(0, (window.outerWidth - window.innerWidth) / 2);
              const browserTopChrome = Math.max(0, window.outerHeight - window.innerHeight - browserLeftBorder);
              best = {
                label: labelText.replace(/\s+/g, " ").trim().slice(0, 120),
                screenX: window.screenX + browserLeftBorder + rect.left,
                screenY: window.screenY + browserTopChrome + rect.top,
                width: rect.width,
                height: rect.height,
                score: candidateScore
              };
              bestElement = element;
            }
          }

          if (!bestElement) return "null";

          if (actionType === "click") {
            bestElement.focus();
            bestElement.click();
            return JSON.stringify({ ok: true, message: "Clicked element", label: best.label });
          } else if (actionType === "type") {
            bestElement.focus();
            bestElement.value = actionValue;
            bestElement.dispatchEvent(new Event('input', { bubbles: true }));
            bestElement.dispatchEvent(new Event('change', { bubbles: true }));
            return JSON.stringify({ ok: true, message: "Typed text into element", label: best.label });
          }

          return JSON.stringify(best);
        })()
        """
        return (
            template.replace("QUERY_PLACEHOLDER", json.dumps(query))
            .replace("ACTION_TYPE_PLACEHOLDER", json.dumps(action_type))
            .replace("ACTION_VALUE_PLACEHOLDER", json.dumps(action_value))
        )

    async def resolve_element_via_cdp(self, query: str) -> Optional[Dict[str, Any]]:
        """Resolves target element details (label, screen coordinates, score) using CDP."""
        js_script = self._get_unified_js(query, action_type="ground")
        result_str = await self.evaluate_js(js_script)
        if not result_str or result_str == "null":
            return None
        try:
            return json.loads(result_str)
        except Exception:
            return None

    async def cdp_click(self, query: str) -> Optional[Dict[str, Any]]:
        """Finds target element and clicks it using CDP evaluate."""
        js_script = self._get_unified_js(query, action_type="click")
        result_str = await self.evaluate_js(js_script)
        if not result_str or result_str == "null":
            return None
        try:
            return json.loads(result_str)
        except Exception:
            return None

    async def cdp_type(self, query: str, text: str) -> Optional[Dict[str, Any]]:
        """Finds target element and types text into it using CDP evaluate."""
        js_script = self._get_unified_js(query, action_type="type", action_value=text)
        result_str = await self.evaluate_js(js_script)
        if not result_str or result_str == "null":
            return None
        try:
            return json.loads(result_str)
        except Exception:
            return None


# Singleton instance
cdp_client = CDPClient()
