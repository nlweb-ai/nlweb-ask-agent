# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Basic config services, including loading config from config_llm.yaml, config_embedding.yaml, config_retrieval.yaml,
config_webserver.yaml, config_nlweb.yaml
WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from __future__ import annotations

import copy
import os
import yaml
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from dotenv import load_dotenv
from typing import Any, TYPE_CHECKING

from nlweb_core.provider_map import ProviderMap

if TYPE_CHECKING:
    from nlweb_core.llm import GenerativeLLMProvider
    from nlweb_core.scoring import ScoringLLMProvider
    from nlweb_core.site_config.base import SiteConfigLookup

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Dataclasses
# =============================================================================


@dataclass
class EmbeddingProviderConfig:
    api_key: str | None = None
    endpoint: str | None = None
    api_version: str | None = None
    model: str | None = None
    config: dict[str, Any] | None = None
    auth_method: str | None = None
    import_path: str | None = None
    class_name: str | None = None


@dataclass
class RetrievalProviderConfig:
    api_key: str | None = None
    api_key_env: str | None = None
    api_endpoint: str | None = None
    api_endpoint_env: str | None = None
    database_path: str | None = None
    index_name: str | None = None
    db_type: str | None = None
    use_knn: bool | None = None
    enabled: bool = False
    vector_type: dict[str, Any] | None = None
    auth_method: str | None = None
    import_path: str | None = None
    class_name: str | None = None


@dataclass
class ServerConfig:
    host: str = "localhost"
    enable_cors: bool = True
    max_connections: int = 100
    timeout: int = 30


@dataclass
class NLWebConfig:
    sites: list[str]
    json_data_folder: str = "./data/json"
    json_with_embeddings_folder: str = "./data/json_with_embeddings"
    chatbot_instructions: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    tool_selection_enabled: bool = True
    memory_enabled: bool = False
    analyze_query_enabled: bool = False
    decontextualize_enabled: bool = True
    required_info_enabled: bool = True
    aggregation_enabled: bool = False
    who_endpoint_enabled: bool = True
    api_keys: dict[str, str] = field(default_factory=dict)
    who_endpoint: str = "http://localhost:8000/who"


@dataclass
class ConversationStorageConfig:
    type: str
    enabled: bool = True
    api_key: str | None = None
    url: str | None = None
    endpoint: str | None = None
    database_path: str | None = None
    auth_method: str | None = None
    collection_name: str | None = None
    database_name: str | None = None
    container_name: str | None = None
    table_name: str | None = None
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    connection_string: str | None = None
    vector_size: int = 1536
    vector_dimensions: int = 1536
    partition_key: str | None = None
    max_conversations: int | None = None
    ttl_seconds: int | None = None
    vector_type: dict[str, Any] | None = None
    rrf: dict[str, Any] | None = None
    knn: dict[str, Any] | None = None


@dataclass
class ObjectLookupConfig:
    type: str
    enabled: bool = True
    endpoint: str | None = None
    database_name: str | None = None
    container_name: str | None = None
    partition_key: str | None = None
    import_path: str | None = None
    class_name: str | None = None


@dataclass
class SiteConfigStorageConfig:
    import_path: str
    class_name: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoringModelConfig:
    """Configuration for a single scoring model provider."""

    import_path: str
    class_name: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerativeModelConfig:
    """Configuration for a single generative model provider."""

    import_path: str
    class_name: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class RankingConfig:
    scoring_questions: list[str] = field(
        default_factory=lambda: ["Is this item relevant to the query?"]
    )


@dataclass
class StorageBehaviorConfig:
    store_anonymous: bool = True
    max_conversations_per_thread: int = 100
    max_threads_per_user: int = 1000
    retention_days: int = 365
    compute_embeddings: bool = True
    batch_size: int = 100
    enable_search: bool = True
    auto_migrate_on_login: bool = True
    max_migrate_conversations: int = 500


# =============================================================================
# AppConfig - Main Configuration Dataclass
# =============================================================================


@dataclass
class AppConfig:
    """
    Main application configuration.

    This is a dataclass that holds all configuration values. The loading logic
    is in the separate load_config() function.
    """

    # Directories
    config_directory: str = ""
    base_output_directory: str | None = None

    # Generative Model Providers
    generative_model_providers: dict[str, GenerativeModelConfig] = field(
        default_factory=dict
    )

    # Embedding Configuration
    embedding_providers: dict[str, EmbeddingProviderConfig] = field(
        default_factory=dict
    )
    preferred_embedding_provider: str | None = None

    # Retrieval Configuration
    retrieval_endpoints: dict[str, RetrievalProviderConfig] = field(
        default_factory=dict
    )
    write_endpoint: str | None = None

    # Conversation Storage
    conversation_storage: ConversationStorageConfig | None = None
    conversation_storage_behavior: StorageBehaviorConfig | None = None
    conversation_storage_endpoints: dict[str, ConversationStorageConfig] = field(
        default_factory=dict
    )
    conversation_storage_default: str = "qdrant_local"

    # Object Storage (Cosmos DB)
    object_storage: ObjectLookupConfig | None = None

    # Site Config Providers
    site_config_providers: dict[str, SiteConfigStorageConfig] = field(
        default_factory=dict
    )

    # Scoring Model Providers
    scoring_model_providers: dict[str, ScoringModelConfig] = field(default_factory=dict)

    # Ranking Configuration
    ranking: RankingConfig | None = None

    # NLWeb Configuration
    nlweb: NLWebConfig | None = None

    # Server Configuration
    server: ServerConfig | None = None
    port: int = 8080
    mode: str = "production"
    nlweb_gateway: str = "nlwm.azurewebsites.net"
    test_user: str = "anonymous"

    # OAuth Configuration
    oauth_providers: dict[str, Any] = field(default_factory=dict)
    oauth_session_secret: str | None = None
    oauth_token_expiration: int = 86400
    oauth_require_auth: bool = False
    oauth_anonymous_endpoints: list[str] = field(default_factory=list)

    # Query methods
    def is_development_mode(self) -> bool:
        """Returns True if the system is running in development mode."""
        return self.mode.lower() == "development"

    def is_testing_mode(self) -> bool:
        """Returns True if the system is running in testing mode."""
        return self.mode.lower() == "testing"

    def should_raise_exceptions(self) -> bool:
        """Returns True if exceptions should be raised instead of caught."""
        return self.is_testing_mode() or self.is_development_mode()

    def get_embedding_provider(
        self, provider_name: str | None = None
    ) -> EmbeddingProviderConfig | None:
        """Get the specified embedding provider config or the preferred one if not specified."""
        if provider_name and provider_name in self.embedding_providers:
            return self.embedding_providers[provider_name]
        if (
            self.preferred_embedding_provider
            and self.preferred_embedding_provider in self.embedding_providers
        ):
            return self.embedding_providers[self.preferred_embedding_provider]
        return None

    # Provider instance accessors (delegate to module-level ProviderMaps)

    def get_generative_provider(self, name: str) -> GenerativeLLMProvider:
        """Get a cached generative LLM provider instance by name."""
        if _generative_provider_map is None:
            raise RuntimeError("Providers not initialized. Call initialize_providers() first.")
        return _generative_provider_map.get(name)

    def get_scoring_provider(self, name: str) -> ScoringLLMProvider:
        """Get a cached scoring LLM provider instance by name."""
        if _scoring_provider_map is None:
            raise RuntimeError("Providers not initialized. Call initialize_providers() first.")
        return _scoring_provider_map.get(name)

    def get_site_config_lookup(self, name: str) -> SiteConfigLookup:
        """Get a cached site config lookup instance by name."""
        if _site_config_provider_map is None:
            raise RuntimeError("Providers not initialized. Call initialize_providers() first.")
        return _site_config_provider_map.get(name)


# =============================================================================
# Module-Level Helper Functions
# =============================================================================


def _get_config_directory() -> str:
    """
    Get the configuration directory from environment variable or use default.
    Default is the config folder at the same level as config.py.
    """
    config_dir = os.getenv("NLWEB_CONFIG_DIR")
    if config_dir:
        config_dir = os.path.expanduser(os.path.expandvars(config_dir))
        if not os.path.exists(config_dir):
            print(
                f"Warning: Configured config directory {config_dir} does not exist. Using default."
            )
            config_dir = None

    if not config_dir:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(current_dir, "config")

    return os.path.abspath(config_dir)


def _get_base_output_directory() -> str | None:
    """
    Get the base directory for all output files from the environment variable.
    Returns None if the environment variable is not set.
    """
    base_dir = os.getenv("NLWEB_OUTPUT_DIR")
    if base_dir and not os.path.exists(base_dir):
        try:
            os.makedirs(base_dir, exist_ok=True)
            print(f"Created output directory: {base_dir}")
        except Exception as e:
            print(f"Warning: Failed to create output directory {base_dir}: {e}")
            return None
    return base_dir


def _resolve_path(
    path: str, config_directory: str, base_output_directory: str | None
) -> str:
    """
    Resolves a path, considering the base output directory if set.
    """
    if os.path.isabs(path):
        return path

    if base_output_directory:
        return os.path.abspath(os.path.join(base_output_directory, path))
    else:
        return os.path.abspath(os.path.join(config_directory, path))


def _get_config_value(value: Any, default: Any = None) -> Any:
    """
    Get configuration value. If value is an env var name, fetch from environment.
    """
    if value is None:
        return default

    if isinstance(value, str):
        if value.endswith("_ENV") or value.isupper():
            return os.getenv(value, default)
        else:
            return value

    return value


# =============================================================================
# Configuration Loading Functions
# =============================================================================


def _load_embedding_config(
    data: dict,
) -> tuple[dict[str, EmbeddingProviderConfig], str | None]:
    """Load embedding configuration from config dict."""
    if "embedding" not in data:
        return {}, None

    emb_cfg = data["embedding"]
    provider_name = emb_cfg.get("provider", "default")

    providers = {
        provider_name: EmbeddingProviderConfig(
            api_key=_get_config_value(emb_cfg.get("api_key_env")),
            endpoint=_get_config_value(emb_cfg.get("endpoint_env")),
            api_version=_get_config_value(emb_cfg.get("api_version")),
            model=_get_config_value(emb_cfg.get("model")),
            config=_get_config_value(emb_cfg.get("config")),
            auth_method=_get_config_value(emb_cfg.get("auth_method"), "api_key"),
            import_path=_get_config_value(emb_cfg.get("import_path")),
            class_name=_get_config_value(emb_cfg.get("class_name")),
        )
    }

    return providers, provider_name


def _load_retrieval_config(
    data: dict,
) -> tuple[dict[str, RetrievalProviderConfig], str | None]:
    """Load retrieval configuration from config dict."""
    if "retrieval" not in data:
        return {}, None

    ret_cfg = data["retrieval"]
    provider_name = ret_cfg.get("provider", "default")

    endpoints = {
        provider_name: RetrievalProviderConfig(
            api_key=_get_config_value(ret_cfg.get("api_key_env")),
            api_key_env=ret_cfg.get("api_key_env"),
            api_endpoint=_get_config_value(ret_cfg.get("api_endpoint_env")),
            api_endpoint_env=ret_cfg.get("api_endpoint_env"),
            database_path=_get_config_value(ret_cfg.get("database_path")),
            index_name=_get_config_value(ret_cfg.get("index_name")),
            db_type=_get_config_value(ret_cfg.get("db_type", provider_name)),
            enabled=ret_cfg.get("enabled", True),
            use_knn=ret_cfg.get("use_knn"),
            vector_type=ret_cfg.get("vector_type"),
            auth_method=_get_config_value(ret_cfg.get("auth_method"), "api_key"),
            import_path=_get_config_value(ret_cfg.get("import_path")),
            class_name=_get_config_value(ret_cfg.get("class_name")),
        )
    }

    return endpoints, provider_name


def _load_conversation_storage(
    data: dict, config_directory: str, base_output_directory: str | None
) -> ConversationStorageConfig:
    """Load conversation storage configuration from config dict."""
    if "conversation_storage" not in data:
        return ConversationStorageConfig(
            type="qdrant",
            enabled=False,
            database_path=_resolve_path(
                "../data/conversations_db", config_directory, base_output_directory
            ),
            collection_name="nlweb_conversations",
        )

    conv_cfg = data["conversation_storage"]
    return ConversationStorageConfig(
        type=conv_cfg.get("type", "qdrant"),
        enabled=conv_cfg.get("enabled", True),
        connection_string=(
            _get_config_value(conv_cfg.get("connection_string_env"))
            if "connection_string_env" in conv_cfg
            else conv_cfg.get("connection_string")
        ),
        host=conv_cfg.get("account_name"),
        url=(
            _get_config_value(conv_cfg.get("url_env"))
            if "url_env" in conv_cfg
            else conv_cfg.get("url")
        ),
        endpoint=(
            _get_config_value(conv_cfg.get("endpoint_env"))
            if "endpoint_env" in conv_cfg
            else conv_cfg.get("endpoint")
        ),
        api_key=(
            _get_config_value(conv_cfg.get("api_key_env"))
            if "api_key_env" in conv_cfg
            else conv_cfg.get("api_key")
        ),
        auth_method=conv_cfg.get("auth_method", "api_key"),
        table_name=conv_cfg.get("table_name"),
        database_path=(
            _resolve_path(
                conv_cfg["database_path"], config_directory, base_output_directory
            )
            if "database_path" in conv_cfg
            else None
        ),
        collection_name=conv_cfg.get("collection_name"),
        database_name=conv_cfg.get("database_name"),
        container_name=conv_cfg.get("container_name"),
        partition_key=conv_cfg.get("partition_key"),
    )


def _load_object_storage(data: dict) -> ObjectLookupConfig:
    """Load object storage configuration from config dict."""
    if "object_storage" not in data:
        return ObjectLookupConfig(type="cosmos", enabled=False)

    obj_cfg = data["object_storage"]
    return ObjectLookupConfig(
        type=obj_cfg.get("type", "cosmos"),
        enabled=obj_cfg.get("enabled", True),
        endpoint=(
            _get_config_value(obj_cfg.get("endpoint_env"))
            if "endpoint_env" in obj_cfg
            else obj_cfg.get("endpoint")
        ),
        database_name=(
            _get_config_value(obj_cfg.get("database_name_env"))
            if "database_name_env" in obj_cfg
            else obj_cfg.get("database_name")
        ),
        container_name=(
            _get_config_value(obj_cfg.get("container_name_env"))
            if "container_name_env" in obj_cfg
            else obj_cfg.get("container_name")
        ),
        partition_key=obj_cfg.get("partition_key"),
        import_path=_get_config_value(obj_cfg.get("import_path")),
        class_name=_get_config_value(obj_cfg.get("class_name")),
    )


def _extract_import_class(
    provider_cfg: dict, config_name: str, provider_name: str
) -> tuple[str, str]:
    """Extract and validate import_path and class_name from provider config."""
    import_path = provider_cfg.get("import_path")
    class_name = provider_cfg.get("class_name")
    if not import_path or not class_name:
        raise ValueError(
            f"{config_name} provider '{provider_name}' must specify import_path and class_name"
        )
    return import_path, class_name


def _build_options(provider_cfg: dict) -> dict[str, Any]:
    """Build options dict from provider config, resolving _env suffixed keys."""
    options: dict[str, Any] = {}
    for key, value in provider_cfg.items():
        if key in ("import_path", "class_name"):
            continue
        if key.endswith("_env"):
            resolved_key = key[:-4]  # Remove _env suffix
            options[resolved_key] = _get_config_value(value)
        else:
            options[key] = value
    return options


def _load_site_config_storage(data: dict) -> dict[str, SiteConfigStorageConfig]:
    """Load site config provider configuration from config dict."""
    if "site_config" not in data:
        return {}

    site_cfg = data["site_config"]
    if not isinstance(site_cfg, dict):
        raise ValueError("site_config must be a mapping of provider names to configs")

    providers: dict[str, SiteConfigStorageConfig] = {}
    for provider_name, provider_cfg in site_cfg.items():
        if not isinstance(provider_cfg, dict):
            raise ValueError(
                f"site_config provider '{provider_name}' must be a mapping"
            )
        import_path, class_name = _extract_import_class(
            provider_cfg, "site_config", provider_name
        )
        providers[provider_name] = SiteConfigStorageConfig(
            import_path=import_path,
            class_name=class_name,
            options=_build_options(provider_cfg),
        )

    return providers


def _load_scoring_model_config(data: dict) -> dict[str, ScoringModelConfig]:
    """Load scoring model provider configuration from config dict."""
    if "scoring_model" not in data:
        return {}

    scoring_cfg = data["scoring_model"]
    if not isinstance(scoring_cfg, dict):
        raise ValueError("scoring_model must be a mapping of provider names to configs")

    providers: dict[str, ScoringModelConfig] = {}
    for provider_name, provider_cfg in scoring_cfg.items():
        if not isinstance(provider_cfg, dict):
            raise ValueError(
                f"scoring_model provider '{provider_name}' must be a mapping"
            )
        import_path, class_name = _extract_import_class(
            provider_cfg, "scoring_model", provider_name
        )
        providers[provider_name] = ScoringModelConfig(
            import_path=import_path,
            class_name=class_name,
            options=_build_options(provider_cfg),
        )

    return providers


def _load_generative_model_config(data: dict) -> dict[str, GenerativeModelConfig]:
    """Load generative model provider configuration from config dict."""
    if "generative_model" not in data:
        return {}

    gen_cfg = data["generative_model"]
    if not isinstance(gen_cfg, dict):
        raise ValueError("generative_model must be a mapping of provider names to configs")

    providers: dict[str, GenerativeModelConfig] = {}
    for provider_name, provider_cfg in gen_cfg.items():
        if not isinstance(provider_cfg, dict):
            raise ValueError(
                f"generative_model provider '{provider_name}' must be a mapping"
            )
        import_path, class_name = _extract_import_class(
            provider_cfg, "generative_model", provider_name
        )
        providers[provider_name] = GenerativeModelConfig(
            import_path=import_path,
            class_name=class_name,
            options=_build_options(provider_cfg),
        )

    return providers


def _load_ranking_config(data: dict) -> RankingConfig:
    """Load ranking configuration from config dict."""
    if "ranking_config" not in data:
        return RankingConfig()

    ranking_cfg = data["ranking_config"]
    scoring_questions = ranking_cfg.get(
        "scoring_questions",
        ["Is this item relevant to the query?"],
    )
    return RankingConfig(
        scoring_questions=scoring_questions,
    )


def _load_server_config(data: dict) -> ServerConfig:
    """Load server configuration from config dict."""
    server_cfg = data.get("server", {})

    return ServerConfig(
        host=_get_config_value(server_cfg.get("host"), "localhost"),
        enable_cors=_get_config_value(server_cfg.get("enable_cors"), True),
        max_connections=_get_config_value(server_cfg.get("max_connections"), 100),
        timeout=_get_config_value(server_cfg.get("timeout"), 30),
    )


def _load_nlweb_config(
    data: dict, config_directory: str, base_output_directory: str | None
) -> NLWebConfig:
    """Load NLWeb configuration from config dict."""
    # Parse sites
    sites_str = _get_config_value(data.get("sites"), "")
    sites_list = (
        [site.strip() for site in sites_str.split(",") if site.strip()]
        if sites_str
        else []
    )

    # Data folders
    json_data_folder = "./data/json"
    json_with_embeddings_folder = "./data/json_with_embeddings"

    if "data_folders" in data:
        json_data_folder = _get_config_value(
            data["data_folders"].get("json_data"), json_data_folder
        )
        json_with_embeddings_folder = _get_config_value(
            data["data_folders"].get("json_with_embeddings"),
            json_with_embeddings_folder,
        )

    # Resolve paths
    if base_output_directory:
        if not os.path.isabs(json_data_folder):
            json_data_folder = os.path.join(base_output_directory, "data", "json")
        if not os.path.isabs(json_with_embeddings_folder):
            json_with_embeddings_folder = os.path.join(
                base_output_directory, "data", "json_with_embeddings"
            )

    # Ensure directories exist
    os.makedirs(json_data_folder, exist_ok=True)
    os.makedirs(json_with_embeddings_folder, exist_ok=True)

    # Load API keys
    api_keys = {}
    if "api_keys" in data:
        for key, value in data["api_keys"].items():
            resolved_value = _get_config_value(value)
            api_keys[key] = resolved_value
            logger.info(
                "Loaded API key value: %s", "set" if resolved_value else "not set"
            )

    return NLWebConfig(
        sites=sites_list,
        json_data_folder=json_data_folder,
        json_with_embeddings_folder=json_with_embeddings_folder,
        chatbot_instructions=data.get("chatbot_instructions", {}),
        headers=data.get("headers", {}),
        tool_selection_enabled=_get_config_value(
            data.get("tool_selection_enabled"), True
        ),
        memory_enabled=_get_config_value(data.get("memory_enabled"), False),
        analyze_query_enabled=_get_config_value(
            data.get("analyze_query_enabled"), False
        ),
        decontextualize_enabled=_get_config_value(
            data.get("decontextualize_enabled"), True
        ),
        required_info_enabled=_get_config_value(
            data.get("required_info_enabled"), True
        ),
        aggregation_enabled=_get_config_value(data.get("aggregation_enabled"), False),
        who_endpoint_enabled=_get_config_value(data.get("who_endpoint_enabled"), True),
        api_keys=api_keys,
        who_endpoint=_get_config_value(
            data.get("who_endpoint"), "http://localhost:8000/who"
        ),
    )


def _load_oauth_config(
    data: dict,
) -> tuple[dict[str, Any], str | None, int, bool, list[str]]:
    """Load OAuth configuration from config dict."""
    oauth_providers = {}
    oauth_session_secret = None
    oauth_token_expiration = 86400
    oauth_require_auth = False
    oauth_anonymous_endpoints = []

    # Load providers
    for provider_name, provider_data in data.get("providers", {}).items():
        if provider_data.get("enabled", False):
            client_id = _get_config_value(provider_data.get("client_id_env"))
            client_secret = _get_config_value(provider_data.get("client_secret_env"))

            if client_id and client_secret:
                oauth_providers[provider_name] = {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_url": provider_data.get("auth_url"),
                    "token_url": provider_data.get("token_url"),
                    "userinfo_url": provider_data.get("userinfo_url"),
                    "emails_url": provider_data.get("emails_url"),
                    "scope": provider_data.get("scope"),
                }

    # Session config
    session_config = data.get("session", {})
    oauth_session_secret = _get_config_value(session_config.get("secret_key_env"))
    if not oauth_session_secret:
        import secrets

        oauth_session_secret = secrets.token_urlsafe(32)
    oauth_token_expiration = session_config.get("token_expiration", 86400)

    # Auth config
    auth_config = data.get("auth", {})
    oauth_require_auth = auth_config.get("require_auth", False)
    oauth_anonymous_endpoints = auth_config.get("anonymous_endpoints", [])

    return (
        oauth_providers,
        oauth_session_secret,
        oauth_token_expiration,
        oauth_require_auth,
        oauth_anonymous_endpoints,
    )


# =============================================================================
# Main Configuration Loading Function
# =============================================================================


def load_config() -> AppConfig:
    """
    Load configuration from files and return an AppConfig instance.

    This function reads YAML and XML configuration files and constructs
    a fully populated AppConfig dataclass.
    """
    load_dotenv()

    config_directory = _get_config_directory()
    base_output_directory = _get_base_output_directory()

    # Try unified config.yaml first
    unified_config_path = os.path.join(config_directory, "config.yaml")

    if os.path.exists(unified_config_path):
        with open(unified_config_path, "r") as f:
            data = yaml.safe_load(f) or {}

        # Load all configurations from unified file
        generative_model_providers = _load_generative_model_config(data)
        embedding_providers, preferred_embedding_provider = _load_embedding_config(data)
        retrieval_endpoints, write_endpoint = _load_retrieval_config(data)
        conversation_storage = _load_conversation_storage(
            data, config_directory, base_output_directory
        )
        object_storage = _load_object_storage(data)
        site_config_providers = _load_site_config_storage(data)
        scoring_model_providers = _load_scoring_model_config(data)
        ranking = _load_ranking_config(data)
        server = _load_server_config(data)
        nlweb = _load_nlweb_config(data, config_directory, base_output_directory)

        # OAuth from separate file or defaults
        oauth_path = os.path.join(config_directory, "config_oauth.yaml")
        if os.path.exists(oauth_path):
            with open(oauth_path, "r") as f:
                oauth_data = yaml.safe_load(f) or {}
            (
                oauth_providers,
                oauth_session_secret,
                oauth_token_expiration,
                oauth_require_auth,
                oauth_anonymous_endpoints,
            ) = _load_oauth_config(oauth_data)
        else:
            (
                oauth_providers,
                oauth_session_secret,
                oauth_token_expiration,
                oauth_require_auth,
                oauth_anonymous_endpoints,
            ) = ({}, None, 86400, False, [])

        return AppConfig(
            config_directory=config_directory,
            base_output_directory=base_output_directory,
            generative_model_providers=generative_model_providers,
            embedding_providers=embedding_providers,
            preferred_embedding_provider=preferred_embedding_provider,
            retrieval_endpoints=retrieval_endpoints,
            write_endpoint=write_endpoint,
            conversation_storage=conversation_storage,
            conversation_storage_behavior=StorageBehaviorConfig(),
            conversation_storage_endpoints={},
            conversation_storage_default="qdrant_local",
            object_storage=object_storage,
            site_config_providers=site_config_providers,
            scoring_model_providers=scoring_model_providers,
            ranking=ranking,
            nlweb=nlweb,
            server=server,
            port=data.get("port", 8080),
            mode=data.get("mode", "production"),
            nlweb_gateway=data.get("nlweb_gateway", "nlwm.azurewebsites.net"),
            test_user=os.getenv("TEST_USER", "anonymous"),
            oauth_providers=oauth_providers,
            oauth_session_secret=oauth_session_secret,
            oauth_token_expiration=oauth_token_expiration,
            oauth_require_auth=oauth_require_auth,
            oauth_anonymous_endpoints=oauth_anonymous_endpoints,
        )

    # No config file - return defaults
    return AppConfig(
        config_directory=config_directory,
        base_output_directory=base_output_directory,
        nlweb=NLWebConfig(sites=[]),
        server=ServerConfig(),
        conversation_storage=ConversationStorageConfig(type="qdrant", enabled=False),
        object_storage=ObjectLookupConfig(type="cosmos", enabled=False),
        site_config_providers={},
        ranking=RankingConfig(),
        conversation_storage_behavior=StorageBehaviorConfig(),
    )


# =============================================================================
# Contextvar Infrastructure
# =============================================================================

# Module-private static config - None until initialize_config() is called
_STATIC_CONFIG: AppConfig | None = None

# Contextvar holds current config - no default, use get_config() to access
_config_var: ContextVar[AppConfig] = ContextVar("config")


# Attributes that can be overridden per-request
OVERRIDABLE_ATTRS = frozenset(
    {
        "tool_selection_enabled",
        "memory_enabled",
        "analyze_query_enabled",
        "decontextualize_enabled",
        "required_info_enabled",
        "aggregation_enabled",
        "who_endpoint_enabled",
        "scoring_questions",
    }
)


def initialize_config() -> AppConfig:
    """
    Initialize the static configuration from files.

    This should be called once at server startup. After this, CONFIG
    can be used to access configuration values.
    """
    global _STATIC_CONFIG
    _STATIC_CONFIG = load_config()
    return _STATIC_CONFIG


def get_config() -> AppConfig:
    """
    Get the current config for this request context.

    Returns the request-specific config if set via set_config_overrides(),
    otherwise returns the static config.
    """
    try:
        return _config_var.get()
    except LookupError:
        if _STATIC_CONFIG is None:
            raise RuntimeError(
                "Configuration not initialized. Call initialize_config() at server startup."
            )
        return _STATIC_CONFIG


def set_config_overrides(overrides: dict[str, Any]) -> None:
    """
    Create a deep copy of static config with overrides applied.

    Called by middleware when request has config override params.
    Only OVERRIDABLE_ATTRS are accepted; others are silently ignored.
    """
    if _STATIC_CONFIG is None:
        raise RuntimeError(
            "Configuration not initialized. Call initialize_config() first."
        )

    # Filter to only overridable attributes
    filtered = {k: v for k, v in overrides.items() if k in OVERRIDABLE_ATTRS}

    if not filtered:
        return  # No valid overrides, keep pointing to static config

    # Deep copy the static config
    config_copy = copy.deepcopy(_STATIC_CONFIG)

    # Apply overrides to the nlweb sub-config (where feature flags live)
    if config_copy.nlweb:
        for attr, value in filtered.items():
            # Skip scoring_questions - it belongs to ranking config
            if attr == "scoring_questions":
                continue
            if hasattr(config_copy.nlweb, attr):
                setattr(config_copy.nlweb, attr, value)

    # Apply scoring_questions to ranking config
    if "scoring_questions" in filtered and config_copy.ranking:
        config_copy.ranking.scoring_questions = filtered["scoring_questions"]

    _config_var.set(config_copy)


def reset_config() -> None:
    """Reset to static config. Called by middleware after request completes."""
    # Reset by removing the contextvar value (will fall back to static)
    try:
        _config_var.get()
        # Token-based reset - set a temporary value then reset to remove it
        if _STATIC_CONFIG is not None:
            token = _config_var.set(_STATIC_CONFIG)
            _config_var.reset(token)
    except LookupError:
        pass  # Already not set


# =============================================================================
# Provider Maps (module-level, initialized by initialize_providers() at startup)
# =============================================================================

_generative_provider_map: ProviderMap | None = None
_scoring_provider_map: ProviderMap | None = None
_site_config_provider_map: ProviderMap | None = None


def initialize_providers(config: AppConfig) -> None:
    """Eagerly create all provider instances from config. Call at server startup."""
    global _generative_provider_map, _scoring_provider_map, _site_config_provider_map
    _generative_provider_map = ProviderMap(
        config=config.generative_model_providers,
        error_prefix="Generative model provider",
    )
    _scoring_provider_map = ProviderMap(
        config=config.scoring_model_providers,
        error_prefix="Scoring model provider",
    )
    _site_config_provider_map = ProviderMap(
        config=config.site_config_providers,
        error_prefix="Site config provider",
    )


async def close_all_providers() -> None:
    """Close all cached provider instances. Call at server shutdown."""
    if _generative_provider_map is not None:
        await _generative_provider_map.close()
    if _scoring_provider_map is not None:
        await _scoring_provider_map.close()
    if _site_config_provider_map is not None:
        await _site_config_provider_map.close()
