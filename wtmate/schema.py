"""JSON shapes the models must return. Built from the game profile, so the
allowed calls and mistake categories change per game."""
from __future__ import annotations

from .profiles import GameProfile


def observation_schema(p: GameProfile) -> dict:
    return {
        "type": "object",
        "properties": {
            "observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "t": {"type": "number", "description": "Seconds from start, copied from the frame label."},
                        "alive": {"type": "boolean"},
                        "situation": {"type": "string", "enum": p.situations},
                        "minimap_grid": {"type": "string", "description": p.grid_hint},
                        "threat": {"type": "string", "description": "One short line: the biggest visible threat, or empty."},
                        "event": {"type": "string", "enum": p.events},
                        "hypotheses": {
                            "type": "array",
                            "description": "Up to 3 short guesses about what is about to happen.",
                            "items": {
                                "type": "object",
                                "properties": {"guess": {"type": "string"}, "likelihood": {"type": "number"}},
                                "required": ["guess", "likelihood"],
                                "additionalProperties": False,
                            },
                        },
                        "call": {"type": "string", "enum": p.calls},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string", "description": "Under 12 words."},
                    },
                    "required": ["t", "alive", "situation", "minimap_grid", "threat", "event",
                                 "hypotheses", "call", "confidence", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["observations"],
        "additionalProperties": False,
    }


def debrief_schema(p: GameProfile) -> dict:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Two or three plain sentences about the session."},
            "mistakes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "t": {"type": "number"},
                        "category": {"type": "string", "enum": p.mistakes},
                        "what_happened": {"type": "string"},
                        "better_option": {"type": "string"},
                        "hypotheses_checked": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "hypothesis": {"type": "string"},
                                    "verdict": {"type": "string", "enum": ["supported", "rejected", "unclear"]},
                                    "evidence": {"type": "string"},
                                },
                                "required": ["hypothesis", "verdict", "evidence"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["t", "category", "what_happened", "better_option", "hypotheses_checked"],
                    "additionalProperties": False,
                },
            },
            "top3": {"type": "array", "description": "The three things to fix next time, most important first. Short and kind.",
                     "items": {"type": "string"}},
            "good_plays": {"type": "array", "items": {"type": "string"}},
            "call_grades": {
                "type": "array",
                "description": "Grade Drill's calls that mattered.",
                "items": {
                    "type": "object",
                    "properties": {
                        "t": {"type": "number"},
                        "call": {"type": "string"},
                        "grade": {"type": "string", "enum": ["right", "wrong", "too late", "unclear"]},
                        "should_have_said": {"type": "string", "description": "One of Drill's allowed calls, or empty."},
                    },
                    "required": ["t", "call", "grade", "should_have_said"],
                    "additionalProperties": False,
                },
            },
            "lessons_updates": {"type": "array", "description": "Short if-then rules for Drill.",
                                "items": {"type": "string"}},
        },
        "required": ["summary", "mistakes", "top3", "good_plays", "call_grades", "lessons_updates"],
        "additionalProperties": False,
    }


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One sentence: the single biggest thing holding the player back."},
        "death_patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "where": {"type": "string", "description": "Grid squares or area, or 'anywhere'."},
                    "why": {"type": "string"},
                    "matches_seen": {"type": "integer"},
                },
                "required": ["where", "why", "matches_seen"],
                "additionalProperties": False,
            },
        },
        "focus_areas": {
            "type": "array",
            "description": "At most 3. Each one is a habit to build over the next few sessions.",
            "items": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "why": {"type": "string"},
                    "practice": {"type": "string", "description": "A concrete exercise for the next 3 to 5 sessions."},
                    "measure": {"type": "string", "description": "How we'll know it improved, using numbers the app tracks."},
                },
                "required": ["goal", "why", "practice", "measure"],
                "additionalProperties": False,
            },
        },
        "progress": {"type": "string", "description": "What has improved or got worse, with numbers."},
        "drill_lessons": {"type": "array", "description": "The full, rewritten lessons-learned list for Drill (max 15 short if-then rules).",
                          "items": {"type": "string"}},
    },
    "required": ["headline", "death_patterns", "focus_areas", "progress", "drill_lessons"],
    "additionalProperties": False,
}
