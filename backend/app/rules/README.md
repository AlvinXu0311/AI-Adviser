# Rule-Based System

This directory contains the rule-based response system for handling common queries without LLM calls.

## Directory Structure

```
rules/
├── __init__.py              # Package initialization
├── README.md                # This file
├── data/                    # Rule data and configurations
│   ├── patterns.json        # Query patterns and templates
│   └── responses.json       # Predefined responses
├── templates/               # Response templates
│   ├── greetings.json       # Greeting templates
│   ├── farewells.json       # Farewell templates
│   └── common_qa.json       # Common Q&A templates
└── patterns/                # Pattern matching rules
    ├── regex_patterns.py    # Regex-based pattern matchers
    └── keyword_patterns.py  # Keyword-based pattern matchers
```

## Purpose

The rule-based system handles:
- Greetings and farewells
- Simple factual queries
- Common FAQ responses
- Navigation help

This reduces LLM API costs and provides faster responses for routine queries.

## Related Service

See: [backend/app/services/rule_based_response_service.py](../services/rule_based_response_service.py)
