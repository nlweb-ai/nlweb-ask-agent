# NLWeb Pi Labs Models

Pi Labs LLM scoring provider for NLWeb.

## Overview

This package provides integration with Pi Labs scoring API for relevance scoring in NLWeb queries.

## Features

- **PiLabsProvider**: LLM provider that uses Pi Labs scoring API
- **PiLabsClient**: HTTP client for Pi Labs API
- Async scoring with httpx and HTTP/2 support
- Thread-safe client initialization

## Installation

```bash
pip install -e packages/providers/pilabs/models
```

## Usage

Configure in your `config.yaml`:

```yaml
llm:
  scoring:
    llm_type: pilabs
    endpoint: "http://localhost:8001/invocations"
    import_path: "nlweb_pilabs_models.llm"
    class_name: "PiLabsProvider"
```

## Requirements

- Python >= 3.11
- httpx with HTTP/2 support
- nlweb_core

## API

The Pi Labs provider expects:
- `request.query`: The user query
- `item.description`: The item to score
- `site.itemType`: The type of item

Returns:
- `score`: Relevance score (0-100)
- `description`: Item description
