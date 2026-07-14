"""
ADELE — Browser Search Engine
================================
Implements the "Antigravity" architecture for DOM searching:
1. Local, heuristic-based scoring (no LLM latency).
2. Fuzzy matching for resilience.
3. Viewport-aware prioritization.
"""

import re
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher

class AntigravitySearcher:
    """
    High-performance DOM searcher inspired by Antigravity architecture.
    Uses heuristic scoring to find elements instantly without LLM roundtrips.
    """
    
    def search(self, query: str, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Search for elements matching the query.
        Returns sorted list of matches by relevance.
        """
        if not nodes:
            return []
            
        query = query.lower().strip()
        scored = []
        
        for node in nodes:
            score = self._score_node(query, node)
            if score > 0:
                # Inject score for debugging/sorting
                node["_score"] = score
                scored.append(node)
                
        # Sort by score descending
        scored.sort(key=lambda x: x["_score"], reverse=True)
        return scored

    def _score_node(self, query: str, node: Dict[str, Any]) -> float:
        import re
        from difflib import SequenceMatcher

        # Extract fields safely
        text = str(node.get("text") or "").lower().strip()
        attributes = node.get("attributes") or {}
        aria_label = str(attributes.get("aria-label") or "").lower().strip()
        placeholder = str(attributes.get("placeholder") or "").lower().strip()
        name = str(attributes.get("name") or "").lower().strip()
        title = str(attributes.get("title") or "").lower().strip()
        alt = str(attributes.get("alt") or "").lower().strip()
        role = str(attributes.get("role") or "").lower().strip()
        tag = str(node.get("tagName") or "").lower().strip()

        # Normalize function
        def normalize(val: str) -> str:
            val = val.lower()
            val = re.sub(r'[^\w\s]+', ' ', val)
            return " ".join(val.split())

        query_norm = normalize(query)
        score = 0.0

        # 1. Exact Matches (Highest Priority)
        if query_norm:
            if query_norm == normalize(text): score = max(score, 100.0)
            elif query_norm == normalize(aria_label): score = max(score, 95.0)
            elif query_norm == normalize(placeholder): score = max(score, 90.0)
            elif query_norm == normalize(name): score = max(score, 85.0)
            elif query_norm == normalize(title): score = max(score, 80.0)
            elif query_norm == normalize(alt): score = max(score, 80.0)

        # 2. Substring & Word Overlap Matches (High Priority)
        if score < 50 and query_norm:
            # Combine all text fields to check overlap
            texts_to_combine = [text, aria_label, placeholder, name, title, alt]
            combined_text = " ".join(filter(None, texts_to_combine))
            text_norm = normalize(combined_text)

            if text_norm:
                if query_norm in text_norm:
                    score = max(score, 82.0 if len(text_norm) <= len(query_norm) * 5 else 72.0)
                elif text_norm in query_norm and len(text_norm) >= 3:
                    score = max(score, 72.0)
                else:
                    query_words = set(query_norm.split())
                    text_words = set(text_norm.split())
                    overlap = len(query_words.intersection(text_words))
                    if overlap > 0:
                        score = max(score, 40.0 + overlap * 12.0)

        # 3. Fuzzy Match (Resilience)
        # Handle typos like "serch" -> "Search" or "Log in" vs "Login"
        if score < 50 and len(query) > 3:
            for field in [text, aria_label, placeholder, name, title, alt]:
                if not field:
                    continue
                # Raw comparison
                ratio = SequenceMatcher(None, query, field).ratio()
                if ratio > 0.8:
                    score = max(score, 40.0)
                # Normalized comparison (handles space differences like "log in" vs "login")
                norm_field = normalize(field)
                if norm_field:
                    no_space_query = query_norm.replace(" ", "")
                    no_space_field = norm_field.replace(" ", "")
                    if no_space_query == no_space_field:
                        score = max(score, 45.0)
                    else:
                        ratio_norm = SequenceMatcher(None, no_space_query, no_space_field).ratio()
                        if ratio_norm > 0.8:
                            score = max(score, 40.0)

        # 4. Role/Tag Boosting (Contextual)
        # If query implies action, boost interactive elements
        is_interactive = tag in ["button", "a", "input", "select", "textarea"] or role in ["button", "link", "textbox", "menuitem"]

        if is_interactive:
            score += 10.0

        return score

# Singleton instance for easy import
search_engine = AntigravitySearcher()