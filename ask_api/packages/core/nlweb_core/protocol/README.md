# NLWeb Protocol Data Models

This folder contains the Pydantic data models that define the NLWeb protocol's request and response structures.

## What's Here

- **`models.py`** - Pydantic models for all protocol types
- **`__init__.py`** - Exports for easy importing

## Models

### Request Models

- `AskRequest` - Natural language query requests
- `WhoRequest` - Agent discovery requests

### Response Models

- `AskResponse` - Query responses with metadata and content
- `WhoResponse` - Agent discovery responses

### Supporting Models

- `ResponseMeta` - Response metadata (supports protocol-specific extensions)
- `TextContent` - Text content items
- `ResourceContent` - Resource content items (structured data)
- `Resource` - Resource container with optional UI rendering info
- `Agent` - Agent/tool descriptions
- `Mode` - Enum for processing modes (list/summary)

## Usage

```python
from nlweb_core.protocol import AskRequest, AskResponse, ResponseMeta, TextContent

# Create a validated request
request = AskRequest(
    query="best pizza restaurants in Seattle",
    mode="list",
    streaming=False
)

# Create a validated response
response = AskResponse(
    meta=ResponseMeta(version="0.5"),
    content=[
        TextContent(
            type="text",
            text="Found 3 great pizza restaurants"
        )
    ]
)

# Serialize to JSON (use by_alias=True for correct field names like _meta)
json_output = response.model_dump(by_alias=True)
```

## Validation

The models automatically validate:

- Required fields are present
- Field types are correct
- Enum values are valid (e.g., mode must be "list" or "summary")
- Arrays have minimum lengths where specified

```python
# This will raise ValidationError - query is required
try:
    request = AskRequest()
except ValidationError as e:
    print(e)

# This will raise ValidationError - mode must be "list" or "summary"
try:
    request = AskRequest(query="test", mode="invalid")
except ValidationError as e:
    print(e)
```

## Source of Truth

These models are generated from the formal TypeSpec specification maintained at:
**https://github.com/nlweb-ai/nlweb-typespec**

The TypeSpec defines the protocol in a language-agnostic way and can generate clients for any programming language.

## Updating the Models

**DO NOT edit `models.py` manually!** Changes will be lost when regenerating.

To update the models:

1. **Make changes in the TypeSpec repo:**

```bash
   cd nlweb-typespec
   # Edit main.tsp
   npx tsp compile .
```

2. **Regenerate Python models:**

```bash
   datamodel-codegen \
     --input tsp-output/openapi/openapi.yaml \
     --output protocol_models.py \
     --input-file-type openapi \
     --output-model-type pydantic_v2.BaseModel \
     --use-standard-collections \
     --use-union-operator
```

3. **Manual adjustments needed after generation:**

   - Fix `Type`/`Type1` enum collisions → use `Literal['text']` and `Literal['resource']`
   - Add `model_config = {"extra": "allow"}` to `ResponseMeta`

4. **Copy to nlweb_core:**

```bash
   cp protocol_models.py ../NLWeb_Core/packages/core/nlweb_core/protocol/models.py
```

5. **Test and commit:**

```bash
   python -c "from nlweb_core.protocol import AskRequest; print('✅ Works!')"
   git add packages/core/nlweb_core/protocol/models.py
   git commit -m "Update protocol models from TypeSpec"
```

## Protocol Extensions

The `ResponseMeta` model allows protocol-specific extensions via `extra="allow"`:

```python
# ChatGPT Apps can add rendering hints
meta = ResponseMeta(
    version="0.5",
    **{"openai/outputTemplate": "ui://widget/restaurant-card.html"}
)

# MCP can add tool information
meta = ResponseMeta(
    version="0.5",
    **{"mcp/toolId": "search-123"}
)
```

## Questions?

See the full protocol specification and documentation at:

- TypeSpec repo: https://github.com/nlweb-ai/nlweb-typespec