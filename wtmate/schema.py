"""The shared vocabulary: what the teammate can say, and the JSON shapes models return."""

# Short calls the fast tier may make. Keep this list small: a teammate who
# talks too much gets muted.
CALLS = [
    "none",
    "check minimap",
    "flank left",
    "flank right",
    "pull back",
    "hold position",
    "push now",
    "change position",
    "angle your armor",
    "cap the point",
]

SITUATIONS = [
    "spawning", "driving to position", "holding position", "in a firefight",
    "flanking", "retreating", "capping", "dead or spectating", "menu or loading", "unclear",
]

EVENTS = ["none", "death", "kill", "hit taken", "hit dealt", "capture", "respawn"]

# Mistake categories the deep tier tags. Stable names let habit memory count
# repeats across matches.
MISTAKES = [
    "ignored minimap threat",
    "pushed alone",
    "stayed in one spot too long",
    "exposed weak armor",
    "bad route or open ground",
    "overextended after a kill",
    "slow to retreat when hurt",
    "missed the objective",
    "poor target choice",
    "other",
]

OBSERVATION_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "t": {"type": "number", "description": "Seconds from start of match, copied from the frame label."},
                    "alive": {"type": "boolean"},
                    "situation": {"type": "string", "enum": SITUATIONS},
                    "minimap_grid": {"type": "string", "description": "Grid square of the player's arrow on the minimap, like 'D4'. Empty if unreadable."},
                    "threat": {"type": "string", "description": "One short line: the biggest visible threat, or empty."},
                    "event": {"type": "string", "enum": EVENTS},
                    "hypotheses": {
                        "type": "array",
                        "description": "Up to 3 short guesses about what is about to happen.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "guess": {"type": "string"},
                                "likelihood": {"type": "number"},
                            },
                            "required": ["guess", "likelihood"],
                            "additionalProperties": False,
                        },
                    },
                    "call": {"type": "string", "enum": CALLS},
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

DEBRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Two or three plain sentences about the match."},
        "mistakes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "t": {"type": "number"},
                    "category": {"type": "string", "enum": MISTAKES},
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
        "top3": {
            "type": "array",
            "description": "The three things to fix next match, most important first. Short and kind.",
            "items": {"type": "string"},
        },
        "good_plays": {"type": "array", "items": {"type": "string"}},
        "call_grades": {
            "type": "array",
            "description": "Grade the fast tier's calls that mattered.",
            "items": {
                "type": "object",
                "properties": {
                    "t": {"type": "number"},
                    "call": {"type": "string"},
                    "grade": {"type": "string", "enum": ["right", "wrong", "too late", "unclear"]},
                    "should_have_said": {"type": "string"},
                },
                "required": ["t", "call", "grade", "should_have_said"],
                "additionalProperties": False,
            },
        },
        "lessons_updates": {
            "type": "array",
            "description": "Short rules for the fast tier, e.g. 'If red dots appear on the left flank of the minimap, call check minimap'.",
            "items": {"type": "string"},
        },
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
                    "where": {"type": "string", "description": "Grid squares or map area, or 'anywhere'."},
                    "why": {"type": "string"},
                    "matches_seen": {"type": "integer"},
                },
                "required": ["where", "why", "matches_seen"],
                "additionalProperties": False,
            },
        },
        "focus_areas": {
            "type": "array",
            "description": "At most 3. Each one is a habit to build over the next few matches.",
            "items": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "why": {"type": "string"},
                    "practice": {"type": "string", "description": "A concrete exercise for the next 3 to 5 matches."},
                    "measure": {"type": "string", "description": "How we'll know it improved, using numbers the app tracks."},
                },
                "required": ["goal", "why", "practice", "measure"],
                "additionalProperties": False,
            },
        },
        "progress": {"type": "string", "description": "What has improved or got worse across matches, with numbers."},
        "drill_lessons": {
            "type": "array",
            "description": "The full, rewritten lessons-learned list for Drill (max 15 short if-then rules).",
            "items": {"type": "string"},
        },
    },
    "required": ["headline", "death_patterns", "focus_areas", "progress", "drill_lessons"],
    "additionalProperties": False,
}
